import json
import logging
import string
import threading
import queue
import time
import os
import pyaudio
from realtimetts_clone.text_to_stream import TextToAudioStream
from lib.sentencequeue import ThreadSafeSentenceQueue, Sentence
from lib.bufferstream import BufferStream
from realtimetts_clone.engines.cosyvoice_engine import CosyvoiceEngine

class TTSHandler:
    """
    Class that handles TTS using Cosyvoice engine.
    Internal flow:
    - Text/emotion is enqueued in the ThreadSafeSentenceQueue (self.sentence_queue)
    - Sentence worker thread reads sentences, chooses the cloning reference, and feeds text into TextToAudioStream
    - TextToAudioStream (backed by CosyVoiceEngine) synthesizes audio and plays audio
    Internal States:
    - config: json containing configuration parameters.
    - references_folder: folder that contains wav files for voice cloning.
    - dbg_log: whether to log debugging statements.
    - stop_event: whether to stop TTS during user interruption.
    - sentence_queue: queue that contains text to be read.
    - chunk_queue: queue that contains audio chunks to be played.
    - chunk_lock: lock that controls access to chunk_queue.
    - pyFormat: format of pyaudio stream.
    - pyChannels: number of audio channels in pyaudio stream.
    - pySampleRate: sample rate of pyaudio stream
    - pyOutput_device_index: index of device to use to play audio.
    - pyaudio_instance: pyaudio instance
    - pystream: pystream instantiated from the pyaudio instance.
    - tts_sentence_thread: sentence queuer thread
    - tts_play_thread: sentence player thread
    - external_interrupt_event: an external interrupt if it arrived
    - _stream_needs_reset: whether the TextToAudioStream needs to be re-built after a user interrupt
    - engine: the cosyvoice engine to synthesize audio with
    - stream: TextToAudioStream which uses the engine to create audio
    """
    def __init__(self, config_file='tts_config.json', gender: string = "female"):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        if gender == "female":
            self.references_folder = self.config['references_folder_female']
        else:
            self.references_folder = self.config['references_folder_male']
        self.dbg_log = self.config['dbg_log']
        self.stop_event = threading.Event()
        self.sentence_queue = ThreadSafeSentenceQueue()
        self.chunk_queue = queue.Queue()
        self.chunk_lock = threading.Lock()
        
        self.pyFormat = pyaudio.paInt16
        self.pyChannels = 1
        self.pySampleRate = 24000
        self.pyOutput_device_index = None
        
        # handles to threads/streams for quick stop
        self.pyaudio_instance = None
        self.pystream = None
        self.tts_sentence_thread = None
        self.tts_play_thread = None
        self.external_interrupt_event = None
        self._stream_needs_reset = False # Set to true when TextToAudioStream needs re-build after barge-in event

        print("Loading TTS")
        self.engine = CosyvoiceEngine(
            model_path=self.config['cosyvoice_model_path'],
            prompt_speech=self.config['cosyvoice_prompt_speech'],
            prompt_text=self.config['cosyvoice_prompt_text']
        )
        
        self.stream = TextToAudioStream(self.engine, muted=True)

        if self.dbg_log:
            print("Test Play TTS")

    def initialize_pyaudio(self):
        """TTS initialized during each ai turn."""
        self.stop_event = threading.Event()
        self.sentence_queue = ThreadSafeSentenceQueue()
        self.chunk_queue = queue.Queue()

        # Rebuild the stream after an interrupt (or if it's None)
        if getattr(self, "_stream_needs_reset", False) or self.stream is None:
            try:
                # If the old object had internal threads, just drop it on the floor.
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
        """The worker thread that processes queued text for synthesis."""
        while not self.stop_event.is_set():
            # abort if external interrupt is set
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            if self.chunk_queue.empty():
                time.sleep(0.001)
                continue
            with self.chunk_lock:
                chunk = self.chunk_queue.get()
            # guard: if we were stopped after get(), break early
            if self.stop_event.is_set():
                break
            # one more guard just before write
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            self.pystream.write(chunk)

    def start_tts(self):
        """The function that actually synthesizes the audio in cosyvoice."""
        def on_audio_chunk(chunk):
            """Function used as each audio chunk is synthesized, adding to audio queue."""
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
        """After a sentence has been worked, it gets fed to the TextToAudio stream which calls cosyvoice."""
        if sentence.get_finished():
            sentence_text = sentence.get_text()
            if not sentence_text or not sentence_text.strip(): # don't play an empty sentence
                return
            if self.dbg_log:
                logging.debug(f"tts_play_sentence complete sentence found, playing {sentence_text}")
                print(sentence_text)
            self.stream.feed(sentence_text)
            if self.dbg_log:
                logging.debug("tts_play_sentence [STARTPLAY]")
            if not self.stream.is_playing():
                self.start_tts()
        else:
            if self.dbg_log:
                logging.debug(f"tts_play_sentence running sentence found, realtime playing")
            buffer = BufferStream()
            last_text = ""
            if self.dbg_log:
                logging.debug(f"ID: {sentence.id}")
                logging.debug(f"EMOTION: {sentence.emotion}")

            while not sentence.get_finished():
                # early exit if stopped
                if self.stop_event.is_set() or (self.external_interrupt_event is not None and self.external_interrupt_event.is_set()):
                    self.stop_now()
                    return
                current_text = sentence.get_text()
                if len(current_text) > len(last_text):
                    new_text = current_text[len(last_text):]
                    buffer.add(new_text)
                    if not self.stream.is_playing():
                        self.stream.feed(buffer.gen())
                        self.start_tts()
                last_text = current_text
                time.sleep(0.002)

            # flush any remaining tail that arrived right as the sentence finished
            final_text = sentence.get_text()
            if len(final_text) > len(last_text):
                tail = final_text[len(last_text):]
                buffer.add(tail)
                # If we never started playback (short sentence, etc.), start now
                if not self.stream.is_playing():
                    self.stream.feed(buffer.gen())
                    self.start_tts()
            
            if self.dbg_log:
                logging.debug(" - feed finished")
            buffer.stop()
        while self.stream.is_playing():
            # early exit during tail play if stopped
            if self.stop_event.is_set() or (self.external_interrupt_event is not None and self.external_interrupt_event.is_set()):
                self.stop_now()
                break
            time.sleep(0.002)

    def tts_sentence_worker_thread(self):
        """Thread that parses incoming ai sentences, switching the voice clone example or enqueuing the text."""
        while not self.stop_event.is_set():
            # abort if external interrupt is set
            if self.external_interrupt_event is not None and self.external_interrupt_event.is_set():
                self.stop_now()
                break
            sentence = self.sentence_queue.get_sentence()

            if sentence:
                # Get the path to the wav emotion file
                emotion = sentence.emotion
                if not emotion or emotion == "None":
                    emotion = "neutral"
                emotion_file = emotion + ".wav"
                path = os.path.join(self.references_folder, emotion_file)

                # Get also the txt
                emotion_file_txt = emotion + ".txt"
                path_txt = os.path.join(self.references_folder, emotion_file_txt)
                extracted_text = None 
                try:
                    with open(path_txt, 'r', encoding='utf-8') as file:
                        # Read the entire file content, which is a single line
                        extracted_text = file.read().strip()
                        
                    logging.debug(f"Extracted Text: '{extracted_text}'")
                except FileNotFoundError:
                    logging.debug(f"Error: The file was not found at {path_txt}")
                except Exception as e:
                    logging.debug(f"An error occurred: {e}")

                # Check if path exists to the speicfic emotion
                if os.path.exists(path):
                    if self.dbg_log:
                        logging.debug(f"Setting TTS Emotion path: {path}")
                    self.engine.set_cloning_reference(path, extracted_text)
                else:
                    if self.dbg_log:
                        logging.debug(f"No emotion found for path: {path}")
                    path = os.path.join(self.references_folder, "neutral.wav")

                    # Check also for the neutral txt
                    path_txt = os.path.join(self.references_folder, "neutral.txt")
                    extracted_text = None 
                    try:
                        with open(path_txt, 'r', encoding='utf-8') as file:
                            # Read the entire file content, which is a single line
                            extracted_text = file.read().strip()
                            
                        logging.debug(f"Extracted Text: '{extracted_text}'")
                    except FileNotFoundError:
                        logging.debug(f"Error: The file was not found at {path_txt}")
                    except Exception as e:
                        logging.debug(f"An error occurred: {e}")

                    # So in theory it should find the neutral voice
                    if os.path.exists(path):
                        if self.dbg_log:
                            logging.debug(f"Setting neutral: {path}")
                        self.engine.set_cloning_reference(path, extracted_text)
                    else:
                        if self.dbg_log:
                            logging.debug(f"CANT FIND EMOTIONS")

                if self.dbg_log:
                    logging.debug(f"TTS found a sentence, running: {sentence.get_finished()}")
                    logging.debug(f" - finished: {sentence.get_finished()}")
                    logging.debug(f" - retrieved: {sentence.retrieved}")
                    logging.debug(f" - popped: {sentence.popped}")
                    logging.debug(f" - id: {sentence.id}")
                self.tts_play_sentence(sentence)
            
            time.sleep(0.002)

    def start_threads(self):
        """Starts the worker & player threads during the ai turn."""
        self.tts_sentence_thread = threading.Thread(target=self.tts_sentence_worker_thread)
        self.tts_sentence_thread.daemon = True
        self.tts_sentence_thread.start()

        self.tts_play_thread = threading.Thread(target=self.tts_play_worker_thread)
        self.tts_play_thread.daemon = True
        self.tts_play_thread.start()

    def add_text(self, text):
        """Adds ai turn text."""
        self.sentence_queue.add_text(text)

    def add_emotion(self, emotion):
        """Adds ai turn emotion."""
        self.sentence_queue.add_emotion(emotion)

    def finish_current_sentence(self):
        """Finishes the current sentence in the sentence queue."""
        self.sentence_queue.finish_current_sentence()

    def is_empty(self):
        """Checks if sentence queue is empty."""
        return self.sentence_queue.is_empty()

    def is_playing(self):
        """Checks if TextToAudio stream is playing"""
        return self.stream.is_playing()
    
    def shutdown_pyaudio(self):
        """Shuts down pyaudio instances at end of ai turn."""
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
        """Shuts down worker and player threads."""
        self.stop_event.set()
        print("Waiting for sentence thread finished")
        if self.tts_sentence_thread is not None:
            self.tts_sentence_thread.join()
        print("Waiting for play thread finished")
        if self.tts_play_thread is not None:
            self.tts_play_thread.join()
        self.engine.shutdown()

    def stop_now(self):
        """
        Panic stop for barge in event:
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
            # ThreadSafeSentenceQueue has an internal Queue;
            # drop current sentence and clear staged text.
            # Here we do the safest thing: mark the current sentence finished and empty future ones.
            self.sentence_queue.finish_current_sentence()
            # If the implementation exposes a .queue, clear it
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

