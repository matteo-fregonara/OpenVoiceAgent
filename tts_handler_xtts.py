import json
import logging
import threading
import queue
import time
import os
import pyaudio
from realtimetts_clone.text_to_stream import TextToAudioStream
from realtimetts_clone.engines.coqui_engine import CoquiEngine
from lib.sentencequeue import ThreadSafeSentenceQueue, Sentence
from lib.bufferstream import BufferStream

class TTSHandler:
    def __init__(self, config_file='tts_config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        self.references_folder = self.config['references_folder']
        self.dbg_log = self.config['dbg_log']
        self.stop_event = threading.Event()
        self.sentence_queue = ThreadSafeSentenceQueue()
        self.chunk_queue = queue.Queue()
        self.chunk_lock = threading.Lock()
        
        self.pyFormat = pyaudio.paInt16
        self.pyChannels = 1
        self.pySampleRate = 24000
        self.pyOutput_device_index = None

        # ===== NEW: hold handles to threads/streams for quick stop =====
        self.pyaudio_instance = None
        self.pystream = None
        self.tts_sentence_thread = None
        self.tts_play_thread = None
        self.external_interrupt_event = None
        self._stream_needs_reset = False # Set to true when TextToAudioStream needs re-build after barge-in event
        # ===============================================================

        print("Loading TTS")
        if self.config['use_local_model']:
            print(f"Trying to create engine: {self.config['specific_model']} {self.config['local_models_path']}")
            self.engine = CoquiEngine(
                specific_model=self.config['specific_model'],
                local_models_path=self.config['local_models_path']
            )
        else:
            self.engine = CoquiEngine()
        
        self.stream = TextToAudioStream(self.engine, muted=True)

        if self.dbg_log:
            print("Test Play TTS")

        self.stream.feed("hi!")  # only small warmup
        self.stream.play(log_synthesized_text=True, muted=True)

    def initialize_pyaudio(self):
        self.stop_event = threading.Event()
        self.sentence_queue = ThreadSafeSentenceQueue()
        self.chunk_queue = queue.Queue()

        # NEW: rebuild the stream after an interrupt (or if it's None)
        if getattr(self, "_stream_needs_reset", False) or self.stream is None:
            try:
                # If the old object had internal threads, just drop it on the floor.
                # (TextToAudioStream usually doesn't need an explicit close)
                pass
            finally:
                self.stream = TextToAudioStream(self.engine, muted=True)
                self._stream_needs_reset = False

        self.pyaudio_instance = pyaudio.PyAudio()
        self.pystream = self.pyaudio_instance.open(
            format=self.pyFormat,
            channels=self.pyChannels,
            rate=self.pySampleRate,
            output_device_index=self.pyOutput_device_index,
            output=True)
        self.pystream.start_stream()

    def set_interrupt_event(self, event):
        """Provide an external Event (eg, barge event) that should stop TTS immediately."""
        self.external_interrupt_event = event

    def tts_play_worker_thread(self):
        while not self.stop_event.is_set():
            # >>> NEW: abort if external interrupt is set
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            if self.chunk_queue.empty():
                time.sleep(0.001)
                continue
            with self.chunk_lock:
                chunk = self.chunk_queue.get()
            # ===== GUARD: if we were stopped after get(), break early =====
            if self.stop_event.is_set():
                break
            # >>> NEW: one more guard just before write
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            # =============================================================
            self.pystream.write(chunk)

    def start_tts(self):
        def on_audio_chunk(chunk):
            with self.chunk_lock:
                self.chunk_queue.put(chunk)

        self.stream.play_async(
            fast_sentence_fragment=True,
            log_synthesized_text=True,
            muted=True,
            on_audio_chunk=on_audio_chunk,
            minimum_sentence_length=10,
            minimum_first_fragment_length=10,
            context_size=5,
            sentence_fragment_delimiters=".?!;:,\n…)]}。",
            force_first_fragment_after_words=999999,
        )

    def tts_play_sentence(self, sentence: Sentence):
        if sentence.get_finished():
            sentence_text = sentence.get_text()
            if not sentence_text or not sentence_text.strip(): # don't play an empty sentence
                return
            if self.dbg_log:
                print(f"tts_play_sentence complete sentence found, playing {sentence_text}")
            self.stream.feed(sentence_text)
            if self.dbg_log:
                print("tts_play_sentence [STARTPLAY]")
            if not self.stream.is_playing():
                self.start_tts()
        else:
            if self.dbg_log:
                print(f"tts_play_sentence running sentence found, realtime playing")
            buffer = BufferStream()
            last_text = ""
            if self.dbg_log:
                print(f"ID: {sentence.id}")
                print(f"EMOTION: {sentence.emotion}")

            while not sentence.get_finished():
                # ===== EARLY EXIT if stopped =====
                if self.stop_event.is_set() or (self.external_interrupt_event is not None and self.external_interrupt_event.is_set()):
                    self.stop_now()
                    return
                # =================================
                current_text = sentence.get_text()
                if len(current_text) > len(last_text):
                    new_text = current_text[len(last_text):]
                    buffer.add(new_text)
                    if not self.stream.is_playing():
                        self.stream.feed(buffer.gen())
                        self.start_tts()
                last_text = current_text
                time.sleep(0.01)
            
            # >>>>> flush any remaining tail that arrived right as the sentence finished
            final_text = sentence.get_text()
            if len(final_text) > len(last_text):
                tail = final_text[len(last_text):]
                buffer.add(tail)
                # If we never started playback (short sentence, etc.), start now
                if not self.stream.is_playing():
                    self.stream.feed(buffer.gen())
                    self.start_tts()
            # <<<<<
            
            if self.dbg_log:
                print(" - feed finished")
            buffer.stop()
        while self.stream.is_playing():
            # ===== EARLY EXIT during tail play if stopped =====
            if self.stop_event.is_set() or (self.external_interrupt_event is not None and self.external_interrupt_event.is_set()):
                self.stop_now()
                break
            # ==================================================
            time.sleep(0.01)

    def tts_sentence_worker_thread(self):
        while not self.stop_event.is_set():
            # >>> abort if external interrupt is set
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            sentence = self.sentence_queue.get_sentence()

            if sentence:
                emotion = sentence.emotion
                if not emotion or emotion == "None":
                    emotion = "neutral"
                emotion_file = emotion + ".wav"
                path = os.path.join(self.references_folder, emotion_file)
                if os.path.exists(path):
                    if self.dbg_log:
                        print(f"Setting TTS Emotion path: {path}")
                    self.engine.set_cloning_reference(path)
                else:
                    if self.dbg_log:
                        print(f"No emotion found for path: {path}")
                    path = os.path.join(self.references_folder, "neutral.wav")
                    if os.path.exists(path):
                        if self.dbg_log:
                            print(f"Setting neutral: {path}")
                        self.engine.set_cloning_reference(path)
                    else:
                        if self.dbg_log:
                            print(f"CANT FIND EMOTIONS")

                if self.dbg_log:
                    print(f"TTS found a sentence, running: {sentence.get_finished()}")
                    print(f" - finished: {sentence.get_finished()}")
                    print(f" - retrieved: {sentence.retrieved}")
                    print(f" - popped: {sentence.popped}")
                    print(f" - id: {sentence.id}")
                self.tts_play_sentence(sentence)
            
            time.sleep(0.01)

    def start_threads(self):
        self.tts_sentence_thread = threading.Thread(target=self.tts_sentence_worker_thread)
        self.tts_sentence_thread.daemon = True
        self.tts_sentence_thread.start()

        self.tts_play_thread = threading.Thread(target=self.tts_play_worker_thread)
        self.tts_play_thread.daemon = True
        self.tts_play_thread.start()

    def add_text(self, text):
        self.sentence_queue.add_text(text)

    def add_emotion(self, emotion):
        self.sentence_queue.add_emotion(emotion)

    def finish_current_sentence(self):
        self.sentence_queue.finish_current_sentence()

    def is_empty(self):
        return self.sentence_queue.is_empty()

    def is_playing(self):
        return self.stream.is_playing()
    
    def shutdown_pyaudio(self):
        if self.pystream is not None:
            try:
                self.pystream.stop_stream()
                self.pystream.close()
            except Exception:
                pass
        if self.pyaudio_instance is not None:
            try:
                self.pyaudio_instance.terminate()
            except Exception:
                pass
        self.pystream = None
        self.pyaudio_instance = None

    def shutdown(self):
        self.stop_event.set()
        print("Waiting for sentence thread finished")
        if self.tts_sentence_thread is not None:
            self.tts_sentence_thread.join()
        print("Waiting for play thread finished")
        if self.tts_play_thread is not None:
            self.tts_play_thread.join()
        self.engine.shutdown()

    # ===== immediate stop used for barge-in =====
    def stop_now(self):
        """
        Panic stop:
        - prevent more writes
        - stop the pyaudio stream immediately
        - clear all pending audio/sentences so playback truly halts
        NOTE: does NOT kill worker threads; they continue for the next turn.
        """
        self.stop_event.set()  # tell workers to bail out of loops ASAP

        # Stop the low-level audio stream if playing
        try:
            if self.pystream is not None and self.pystream.is_active():
                self.pystream.stop_stream()
        except Exception:
            pass

        # Flush any pending audio data
        with self.chunk_lock:
            try:
                while not self.chunk_queue.empty():
                    self.chunk_queue.get_nowait()
            except Exception:
                pass
        
        # Flush any pending sentences (prevents tail playback resuming)
        try:
            # ThreadSafeSentenceQueue from your lib likely has an internal Queue;
            # use its public API to drop current sentence and clear staged text.
            # Here we do the safest thing: mark the current sentence finished and empty future ones.
            self.sentence_queue.finish_current_sentence()
            # If the implementation exposes a .queue, clear it defensively:
            if hasattr(self.sentence_queue, "queue"):
                with self.sentence_queue.mutex:
                    self.sentence_queue.queue.clear()
        except Exception:
            pass

        # Also tell engine stream to stop if it has such a method
        try:
            if hasattr(self.stream, "stop"):
                self.stream.stop()
                self._stream_needs_reset = True # mark for rebuild
        except Exception:
            self._stream_needs_reset = True

        # Important: allow subsequent turns
        # (recreate fresh stop_event when initialize_pyaudio() is called next)
