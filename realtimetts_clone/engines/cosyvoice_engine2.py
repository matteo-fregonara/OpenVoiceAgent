from .base_engine import BaseEngine
import torch.multiprocessing as mp
from threading import Lock
from .safepipe import SafePipe
from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
import numpy as np

class CosyvoiceEngine(BaseEngine):
    def __init__(self, model_path, prompt_speech, prompt_text, device='cpu'):
        super().__init__()
        self.model_path = model_path
        # load prompt audio at 16k
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
        # instantiate CosyVoice2 once in worker
        model = CosyVoice2(model_path, load_jit=False, load_trt=False, load_vllm=False, fp16=False)
        ready_event.set()

        while True:
            msg = conn.recv()
            if msg["command"] == "shutdown":
                break
            elif msg["command"] == "synthesize":
                text = msg["data"]["text"]

                # non-streaming inference
                # This yields one dict per text chunk
                all_audio_bytes = b''
                for output in model.inference_zero_shot(
                    tts_text=text,
                    prompt_text=prompt_text,
                    prompt_speech_16k=prompt_speech_16k,
                    stream=False
                ):
                    audio_tensor = output['tts_speech']  # shape (1, n_samples)
                    audio = audio_tensor.numpy().astype(np.float32)
                    all_audio_bytes += audio.tobytes()

                # send once at end
                conn.send(("success", all_audio_bytes))
                conn.send(("finished", ""))

    def synthesize(self, text: str):
        with self._synthesize_lock:
            self.parent_synthesize_pipe.send({"command": "synthesize", "data": {"text": text}})
            status, result = self.parent_synthesize_pipe.recv()
            # You’ll get a single big audio bytes block
            while "finished" not in status:
                if isinstance(result, bytes):
                    self.queue.put(result)  # put the whole audio in the queue
                status, result = self.parent_synthesize_pipe.recv()
