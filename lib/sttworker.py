import logging
import threading
import time
from lib.bargecontroller import BargeInController
from RealtimeSTT import AudioToTextRecorder

class STTWorker(threading.Thread):
    """
    Continuously pulls finalized utterances from RealtimeSTT and enqueues them.
    This keeps main loop non-blocking and ready to cancel AI at any time.
    """
    def __init__(self, recorder: AudioToTextRecorder, ctrl: BargeInController, logger=None):
        super().__init__(daemon=True)
        self.recorder = recorder
        self.ctrl = ctrl
        self._stop = threading.Event()
        self.log = logger or logging.getLogger(__name__)

    def run(self):
        while not self._stop.is_set():
            try:
                text = self.recorder.text()  # blocks until user finishes
                if text and text.strip():
                    self.ctrl.input_queue.put(text.strip())
            except Exception as e:
                self.log.exception(f"STTWorker error: {e}")
                time.sleep(0.05)

    def stop(self):
        self._stop.set()