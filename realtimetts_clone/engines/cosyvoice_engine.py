import sys
import os
sys.path.append('third_party/CosyVoice')

matcha_path = os.path.join(os.path.dirname(__file__), '..', '..', 'third_party', 'CosyVoice', 'third_party', 'Matcha-TTS')
sys.path.append(matcha_path)

print('\n'.join(sys.path))

from .base_engine import BaseEngine
import torch.multiprocessing as mp
from threading import Lock
from .safepipe import SafePipe
from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
import numpy as np
import pyaudio

os.environ["TQDM_DISABLE"] = "1"

class CosyvoiceEngine(BaseEngine):
    """
    Class to handle the TTS model CosyVoice2.
    Internal States:
    - model_path: path to local model
    - prompt_speech_16k: the wav file to be used for voice cloning
    - prompt_text: text to be voiced
    - _synthesize_lock: lock that controls so theres only one generation at a time?
    """
    def __init__(self, model_path, prompt_speech, prompt_text):
        super().__init__()
        self.model_path = model_path
        # load prompt audio at 16k
        self.prompt_speech_16k = load_wav(prompt_speech, 16000)
        self.prompt_text = prompt_text
        self._synthesize_lock = Lock()
        self.post_init()

    def set_cloning_reference(self, path, prompt_text=None):
        """Set the voice cloning path and prompt text for new generation."""
        self.prompt_speech_16k = load_wav(path, 16000)
        if prompt_text:
            self.prompt_text = prompt_text
        else:
            self.prompt_text = ""  # fallback

    def post_init(self):
        """Start the engine."""
        self.engine_name = "cosyvoice"
        self.create_worker_process()

    def get_stream_info(self):
        """Get the information needed by the TextToAudioStream playback function."""
        # fallback if cosvoice not initialised
        sr = 16000
        if hasattr(self, "cosyvoice") and hasattr(self.cosyvoice, "sample_rate"):
            sr = self.cosyvoice.sample_rate
        return pyaudio.paFloat32, 1, sr


    def create_worker_process(self):
        """Create the worker thread for cosyvoice."""
        self.parent_synthesize_pipe, child_pipe = SafePipe()
        self.main_ready_event = mp.Event()
        self.synthesize_process = mp.Process(
            target=CosyvoiceEngine._synthesize_worker,
            args=(child_pipe, self.main_ready_event,
                  self.model_path, self.prompt_speech_16k, self.prompt_text)
        )
        self.synthesize_process.start()
        self.main_ready_event.wait()

    @staticmethod
    def _synthesize_worker(conn, ready_event, model_path, prompt_speech_16k, prompt_text):
        """Synthesize worker thread for cosyvoice."""
        # instantiate CosyVoice2 once in worker
        model = CosyVoice2(model_path, load_jit=False, load_trt=False, load_vllm=False, fp16=True)
        ready_event.set()

        while True:
            msg = conn.recv()
            if msg["command"] == "shutdown":
                break
            elif msg["command"] == "synthesize":
                text = msg["data"]["text"]
                updatedSpeech = msg["data"]["prompt_speech_16k"]
                updatedText = msg["data"]["prompt_text"]

                # Streaming inference
                for output in model.inference_zero_shot(
                    tts_text=text,
                    prompt_text=updatedText,
                    prompt_speech_16k=updatedSpeech,
                    stream=True
                ):
                    audio_tensor = output['tts_speech']
                    audio = audio_tensor.numpy().astype(np.float32)  # (1, n_samples)
                    audio_bytes = audio.tobytes()
                    conn.send(("chunk", audio_bytes))  # send each chunk immediately

                # after loop ends
                conn.send(("finished", ""))
    

    def synthesize(self, text: str):
        """Synthesize audio without a worker."""
        try:
            # streaming inference
            with self._synthesize_lock:
                self.parent_synthesize_pipe.send({
                    "command": "synthesize",
                    "data": {
                        "text": text,
                        "prompt_speech_16k": self.prompt_speech_16k,
                        "prompt_text": self.prompt_text
                    }
                })
                while True:
                    status, result = self.parent_synthesize_pipe.recv()
                    if status == "chunk":
                        self.queue.put(result)  # streaming audio chunk
                    elif status == "finished":
                        break
        except Exception as e:
            return False # needs to return False on failure.

        # Needs to return True on success!
        return True
