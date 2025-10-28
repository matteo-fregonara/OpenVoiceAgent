import logging
import threading
import time
from lib.bargecontroller import BargeInController
from RealtimeSTT import AudioToTextRecorder

class STTWorker(threading.Thread):
    """
    Continuously pulls finalized utterances from RealtimeSTT and enqueues them.
    This keeps main loop non-blocking and ready to cancel AI at any time.

    Internal States:
    - recorder: AudioToTextRecorder from RealtimeSTT
    - ctrl: barge event handler that manages ai and user turns
    - _stop: threading event that indicates when STT should stop
    - log: logger to be used for statments
    """
    def __init__(self, recorder: AudioToTextRecorder, ctrl: BargeInController, logger=None):
        super().__init__(daemon=True)
        self.recorder = recorder
        self.ctrl = ctrl
        self._stop = threading.Event()
        self.log = logger or logging.getLogger(__name__)

    def run(self):
        """Runs the STT worker, will put processed user text onto the input queue"""
        while not self._stop.is_set():
            try:
                text = self.recorder.text()  # blocks until user finishes
                if text and text.strip():
                    self.ctrl.input_queue.put(text.strip())
            except Exception as e:
                self.log.exception(f"STTWorker error: {e}")
                time.sleep(0.05)

    def stop(self):
        """Stops the STT worker."""
        self._stop.set()
