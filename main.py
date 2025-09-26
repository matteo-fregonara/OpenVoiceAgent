import os, sys
conda = os.environ.get("CONDA_PREFIX") or sys.prefix
extra = [
    rf"{conda}\Lib\site-packages\nvidia\cuda_runtime\bin",
    rf"{conda}\Lib\site-packages\nvidia\cublas\bin",
    rf"{conda}\Lib\site-packages\nvidia\cudnn\bin",
    rf"{conda}\Lib\site-packages\nvidia\cuda_nvrtc\bin",
]
os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH","")])


import os
import re
import time
import json
import logging
import argparse
from typing import List
from dataclasses import dataclass
from tts_handler import TTSHandler
from RealtimeSTT import AudioToTextRecorder
from llm_lmstudio.llm_handler import LLMHandler
from lib.bargecontroller import BargeInController
from lib.sttworker import STTWorker
from lib.micenergywatcher import MicEnergyWatcher

# Interruptions
# ===== NEW: imports for barge-in controller/workers =====
import threading
import queue
import signal # for forced ctrl c shutdown
# ========================================================

@dataclass
class Config:
    llm_provider: str = "lmstudio"  # "llamacpp" or "ollama" or "openai" or "anthropic" or "lmstudio"
    print_emotions: bool = True
    print_llm_text: bool = True
    use_tts: bool = True
    dbg_log: bool = False
    log_level_nondebug = logging.WARNING
    references_folder: str = "reference_wavs"
    stt_model: str = "tiny.en"
    stt_language: str = "en"
    stt_silence_duration: float = 0.2
    prompt_file: str = "prompts/default.json"    # default; can be overridden via --prompt-file
    tts_config_file: str = "tts_config.json"
    output_file: str = "outputs/example.txt"              # default; can be overridden via --output-file
    silence_timeout: float = 5.0
    silence_token: str = "(says nothing)"


def color_text(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"

class Main:
    def __init__(self, config: Config):
        self.config = config
        self.setup_logging()
        self.valid_emotions = self.get_valid_emotions()

        # Load chat parameters
        with open(config.prompt_file, 'r') as f:
            self.chat_params = json.load(f)

        print("Loading STT")
        self.recorder = AudioToTextRecorder(
            model=config.stt_model,
            language=config.stt_language,
            spinner=False,
            post_speech_silence_duration=config.stt_silence_duration,
        )
        self.llm_handler = LLMHandler()


        self.tts_handler = TTSHandler(config.tts_config_file) if config.use_tts else None        
        
        # Token processing state
        self.plain_text = ""
        self.last_plain_text = ""
        self.buffer = ""
        self.in_emotion = False
        self.last_char = ""
        self.assistant_text = ""  # New variable to store complete assistant response

        # ===== barge-in controller and workers =====
        self.ctrl = BargeInController()
        self.stt_worker = STTWorker(self.recorder, self.ctrl, logger=logging.getLogger("STTWorker"))
        # Optional mic watcher for early barge-in; safe to disable by commenting if not needed
        self.mic_watcher = MicEnergyWatcher(self.ctrl, mode="high_thresh_while_tts", logger=logging.getLogger("MicWatcher"))
        # =================================================

        # Global shutdown variables
        self.shutdown_event = threading.Event() # global exit application flag
        self._sigint_count = 0

        # Start gate variable
        self._first_turn = True

        self._install_signal_handlers()
    
    def setup_logging(self):
        level = logging.DEBUG if self.config.dbg_log else self.config.log_level_nondebug
        logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')

    def get_valid_emotions(self) -> List[str]:
        with open(self.config.tts_config_file, 'r') as f:
            tts_config = json.load(f)
        references_folder = tts_config['references_folder']
        return [os.path.splitext(f)[0] for f in os.listdir(references_folder) if f.endswith('.wav')]        

    def print_available_emotions(self):
        emotions_str = ', '.join(f'(\033[0;91m{emotion.lower()}\033[0m)' for emotion in self.valid_emotions)
        print(f"Available emotions: {emotions_str}\n")

    def print_character_info(self):

        char_name = color_text(self.chat_params['char'], '96')  # Light Cyan
        user_name = color_text(self.chat_params['user'], '93')  # Light Yellow
        char_desc = self.chat_params['char_description'].format(char=self.chat_params['char'])
        user_desc = self.chat_params['user_description'].format(user=self.chat_params['user'])
        scenario = color_text(self.chat_params['scenario'].format(char=self.chat_params['char'], user=self.chat_params['user']), '94')  # Light Blue

        print(f"Assistant Name: {char_name}")
        print(f"Description: {char_desc}")
        print(f"\nUser Name: {user_name}")
        print(f"Description: {user_desc}")
        print(f"\nScenario: {scenario}")
        print()  # Extra line for spacing

    def _print_listen_prompt(self, first: bool = False):
        """
        >>> NEW: Show a visible 'please speak' prompt before we block waiting
        for the first (and subsequent) user utterance.
        """
        user_name = color_text(self.chat_params['user'], '93')
        print(f"\n>>> {user_name}: ", end="", flush=True)

    def get_system_prompt(self) -> str:
        valid_emotions_str = ', '.join(f'[{emotion}]' for emotion in self.valid_emotions)
        
        # Replace placeholders in the system prompt
        system_prompt = self.chat_params['system_prompt'].format(
            char=self.chat_params['char'],
            user=self.chat_params['user'],
            char_description=self.chat_params['char_description'].format(char=self.chat_params['char']),
            user_description=self.chat_params['user_description'].format(user=self.chat_params['user']),
            scenario=self.chat_params['scenario'].format(char=self.chat_params['char'], user=self.chat_params['user']),
            valid_emotions_str=valid_emotions_str
        )
        
        return system_prompt

    def process_llm_token(self, token: str):
        # ===== cooperative cancel check on each token =====
        if self.ctrl.cancel_event.is_set() or self.ctrl.barge_event.is_set():
            # Raise to abort streaming immediately (caught by caller)
            raise RuntimeError("CancelledByBargeIn")
        # ==========================================================
        for char in token:
            self.assistant_text += char  # Add each character to the complete assistant text
            # if char == ' ' and self.last_char == ']':
            #     continue
            if char == '[':
                if self.buffer:
                    self.process_buffer()
                self.buffer = '['
                self.in_emotion = True
            elif char == ']' and self.in_emotion:
                self.buffer += ']'
                self.process_emotion()
                self.buffer = ""
                self.in_emotion = False
            else:
                self.buffer += char
                if not self.in_emotion and self.buffer:
                    self.process_buffer()
            self.last_char = char

    def process_buffer(self):
        new_text = self.process_plain_text(self.buffer)
        if self.tts_handler:
            self.tts_handler.sentence_queue.add_text(new_text)
        self.buffer = ""

    def process_plain_text(self, text: str) -> str:
        self.plain_text += text
        self.plain_text = re.sub(r'\n', '', self.plain_text)    # Remove all linebreaks
        self.plain_text = re.sub(r'^\s+', '', self.plain_text)
        self.plain_text = re.sub(r'\s+', ' ', self.plain_text)  # Replace multiple whitespaces with a single space
        new_text = self.plain_text[len(self.last_plain_text):]
        self.last_plain_text = self.plain_text
        if self.config.print_llm_text:
            print(f"\033[96m{new_text}\033[0m", end='', flush=True)
        return new_text

    def process_emotion(self):
        emotion = self.buffer[1:-1].lower()
        current_emotion = "neutral" if emotion not in self.valid_emotions else emotion
        if self.config.print_emotions:
            print(f"(\033[0;91m{current_emotion.lower()}\033[0m) ", end='', flush=True)
        if self.tts_handler:
            self.tts_handler.sentence_queue.add_emotion(current_emotion)

    def _announce_ai_turn(self):
        char_name = color_text(self.chat_params['char'], '96')
        print(f"<<< {char_name}: ", end="", flush=True)

    def run(self):
        self.print_available_emotions()
        self.print_character_info()
        system_prompt = self.get_system_prompt()

        # --- Prompt user to start scenario (models are already loaded in __init__) ---
        try:
            print("\nModels are loaded and ready.", flush=True)
            input(color_text("Start scenario?  (press Enter to begin, Ctrl+C to exit) ", "32"))
        except KeyboardInterrupt:
            # Allow clean exit BEFORE any background threads start
            if hasattr(self, "_begin_shutdown"):
                self._begin_shutdown()
            return

        # Instead of having a while loop that loops between user input and AI input
        # Need multithreading where there is one thread to process user input and whenever the user is speaking, the AI thread gets interrupted
        # Meanwhile the AI thread processes any previous user input and responds as normal
        # Basically it allows the user to interrupt the AI when it is speaking
        
        # ===== start background workers =====
        self.stt_worker.start()
        self.mic_watcher.start()
        # =========================================

        # >>> ensure clean slate and PROMPT user for the FIRST turn
        self.ctrl.reset_for_next_turn()            # clear any stale events before first turn
        self._print_listen_prompt(first=True)      # visible "please speak" prompt

        # ===== event-driven loop (no blocking input) =====
        try:
            while not self.shutdown_event.is_set():
                # Wait for finalized user utterance
                user_text = self._get_and_drain_input(config.silence_timeout, config.silence_token) # drains + merges (empty in batches instead of single items)

                # print user text
                print(f"{color_text(user_text, '93')}")

                # Change first turn variable
                if self._first_turn: self._first_turn = False

                # If the user started speaking during AI speech, cancel current streams
                if self.ctrl.barge_event.is_set() and self.ctrl.ai_speaking.is_set():
                    self._cancel_ai_now()

                # Run one AI turn cooperatively cancellable
                self._run_ai_turn(user_text, system_prompt)

                # >>> PROMPT the user again for the next turn
                self._print_listen_prompt()
        except KeyboardInterrupt:
            self._begin_shutdown()
        finally:
            # graceful shutdown
            try:
                self.mic_watcher.stop()
            except: pass
            try:
                self.stt_worker.stop()
            except: pass
            try:
                self.cleanup()
            except: pass
        # ======================================================

    def _get_and_drain_input(self, silence_timeout: float = 5.0, silence_token: str = "(says nothing)") -> str | None:
        """
        Blocks for the first item up to `silence_timeout` seconds.
            - If nothing arrives, return the `silence_token`.
            - Otherwise, drain everything currently queued, and returns
            a single merged string.
        """
        # 1) Block for the first item
        try:
            if self._first_turn:
                first = self.ctrl.input_queue.get() # no timeout on the first turn
            else:
                first = self.ctrl.input_queue.get(timeout=silence_timeout)  # <- this is your current blocking call
        except queue.Empty: # nothing arrived within timeout
            return silence_token

        # Something arrived
        parts = [first]

        # 2) Drain everything that's already there, non-blocking
        while True:
            try:
                item = self.ctrl.input_queue.get_nowait()
            except queue.Empty:
                break
            parts.append(item)

        merged = " ".join(s.strip() for s in parts if s)
        return re.sub(r"\s+", " ", merged).strip()

    def _cancel_ai_now(self):
        """
        Hard stop TTS and ask LLM to abort. Clears events after.
        """
        self.ctrl.request_cancel()
        if self.tts_handler:
            self.tts_handler.stop_now()  # NEW: immediate audio stop + clear queues
        # If your LLM handler supports aborting network stream, call it:
        try:
            if hasattr(self.llm_handler, "abort"):
                self.llm_handler.abort()
        except Exception:
            pass
        # Do not reset events here; next turn will do it.

    def _reset_token_state(self):
        # Reset token processing state
        self.plain_text = ""
        self.last_plain_text = ""
        self.buffer = ""
        self.in_emotion = False
        self.last_char = ""
        self.assistant_text = ""
    
    def _run_ai_turn(self, user_text: str, system_prompt: str):
        self._announce_ai_turn()
        self.llm_handler.add_user_text(user_text)
        self._reset_token_state()

        # Let controller know AI is "speaking" (streaming tokens/tts)
        self.ctrl.reset_for_next_turn()  # clear barge/cancel for this turn
        self.ctrl.ai_speaking.set()

        if self.tts_handler:
            self.tts_handler.initialize_pyaudio()
            self.tts_handler.start_threads()
            # >>> NEW: give TTS direct access to barge_event so it can self-stop
            self.tts_handler.set_interrupt_event(self.ctrl.barge_event)
        
        try:
            # Wrap token callback to inject cancellation
            def _on_tok(tok):
                # early barge-in: if user starts talking mid-stream, cancel right away
                if self.ctrl.barge_event.is_set() or self.ctrl.cancel_event.is_set():
                    self.ctrl.request_cancel()
                    raise RuntimeError("CancelledByBargeIn")
                self.process_llm_token(tok)

            self.llm_handler.generate_response(system_prompt, on_token=_on_tok)

            # Process any remaining buffer content
            if self.buffer:
                self.process_buffer()

            # Add the complete assistant text to chat history (unless cancelled)
            if not self.ctrl.cancel_event.is_set():
                self.llm_handler.add_assistant_text(self.assistant_text)

        except RuntimeError as e:
            # Silent/clean abort on our cancellation reason
            if "CancelledByBargeIn" not in str(e):
                raise
            # Optionally log: interrupted assistant turn
        finally:
            if self.tts_handler:
                if not (self.ctrl.cancel_event.is_set() or self.shutdown_event.is_set()):
                    self.tts_handler.sentence_queue.finish_current_sentence()
                self.llm_handler.write_payload(file_path=config.output_file)
                # If we were cancelled, we already stopped TTS in _cancel_ai_now()
                if not (self.ctrl.cancel_event.is_set() or self.shutdown_event.is_set()):
                    self.wait_for_tts_completion()
                # Always stop audio threads cleanly between turns
                self.tts_handler.stop_event.set()
                if getattr(self.tts_handler, "tts_sentence_thread", None):
                    self.tts_handler.tts_sentence_thread.join(timeout=1.0)
                if getattr(self.tts_handler, "tts_play_thread", None):
                    self.tts_handler.tts_play_thread.join(timeout=1.0)
                self.tts_handler.shutdown_pyaudio()
            self.ctrl.ai_speaking.clear()
    
    def wait_for_tts_completion(self):
        if not self.tts_handler:
            return
        logging.debug("Waiting for TTS to finish processing...")
        not_playing_start_time = None
        while not self.shutdown_event.is_set():
            # >>> NEW: detect barge-in during TTS playout
            if self.ctrl.barge_event.is_set():
                logging.debug("Barge detected during TTS playout; cancelling now.")
                self._cancel_ai_now()   # calls tts_handler.stop_now(), clears queues, stops stream
                break                   # exit the wait immediately
            
            if self.tts_handler.sentence_queue.is_empty():
                finished_playout = (
                    not self.tts_handler.stream.is_playing() and
                    self.tts_handler.sentence_queue.is_empty() and
                    self.tts_handler.chunk_queue.empty()
                )
                if finished_playout:
                    if not_playing_start_time is None:
                        not_playing_start_time = time.time()
                    if time.time() - not_playing_start_time >= 0.5:
                        break
                else:
                    not_playing_start_time = None
            time.sleep(0.01)
        logging.debug("All sentences processed and TTS playback completed.")

    def cleanup(self):
        if self.tts_handler:
            logging.debug("Shutting down TTS engine...")
            self.tts_handler.engine.shutdown()
            logging.debug("TTS shutdown complete.")

    def _install_signal_handlers(self):
        def _handler(signum, frame):
            self._sigint_count += 1
            if self._sigint_count == 1:
                print("\n^C received — shutting down gracefully...")
                self._begin_shutdown()
            else:
                print("\n^C again — forcing exit.")
                os._exit(1)  # last resort; avoid hanging forever
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def _begin_shutdown(self):
        """One-shot graceful shutdown: cancel everything and unblock any waits."""
        if self.shutdown_event.is_set():
            return
        self.shutdown_event.set()

        # cancel AI work and audio immediately
        try:
            self._cancel_ai_now()
        except Exception:
            pass

        # stop background threads
        try:
            self.mic_watcher.stop()
        except Exception:
            pass
        try:
            self.stt_worker.stop()
        except Exception:
            pass

        # unblock the main loop if it's waiting on input_queue.get()
        try:
            self.ctrl.input_queue.put_nowait(None)   # sentinel
        except Exception:
            pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Voice chat runner")
    parser.add_argument("-p", "--prompt-file", dest="prompt_file", default=None, help="Path to file to use for prompt parameters")
    parser.add_argument("-o", "--output-file", dest="output_file", default=None, help="Path to file to use for output file")
    args = parser.parse_args()

    prompt_file_path = args.prompt_file or Config.prompt_file
    output_file_path = args.output_file or Config.output_file

    config = Config(prompt_file=prompt_file_path, output_file=output_file_path)
    main = Main(config)
    try:
        main.run()
    except KeyboardInterrupt:
        main._begin_shutdown()
    finally:
        # if some 3rd-party thread refuses to die, force the process to exit
        if main.shutdown_event.is_set():
            time.sleep(0.2)
            os._exit(0)