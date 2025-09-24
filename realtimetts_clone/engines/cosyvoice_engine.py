from .base_engine import BaseEngine
import torch.multiprocessing as mp
from threading import Lock
from .safepipe import SafePipe
from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
import torchaudio
import numpy as np

class CosyvoiceEngine(BaseEngine):
    def __init__(self, model_path, prompt_speech, prompt_text, device='cpu'):
        super().__init__()
        self.model_path = model_path
        self.prompt_speech_16k = load_wav(prompt_speech, 16000)
        self.prompt_text = prompt_text
        self.device = device
        self._synthesize_lock = Lock()
        self.post_init()

    def post_init(self):
        self.engine_name = "cosyvoice"
        self.create_worker_process()

    def create_worker_process(self):
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
        model = CosyVoice2(model_path, load_jit=False, load_trt=False, load_vllm=False, fp16=False)
        ready_event.set()

        while True:
            msg = conn.recv()
            if msg["command"] == "shutdown":
                break
            elif msg["command"] == "synthesize":
                text = msg["data"]["text"]
                # stream audio chunks
                for chunk in model.inference_zero_shot(
                    tts_text=text,
                    prompt_text=prompt_text,
                    prompt_speech_16k=prompt_speech_16k,
                    stream=True
                ):
                    audio_tensor = chunk['tts_speech']  # (1, samples)
                    audio = audio_tensor.numpy().astype(np.float32)
                    conn.send(("success", audio.tobytes()))
                conn.send(("finished", ""))

    def synthesize(self, text: str):
        with self._synthesize_lock:
            self.parent_synthesize_pipe.send({"command": "synthesize", "data": {"text": text}})
            status, result = self.parent_synthesize_pipe.recv()
            while "finished" not in status:
                if isinstance(result, bytes):
                    self.queue.put(result)  # put audio chunk in queue
                status, result = self.parent_synthesize_pipe.recv()
