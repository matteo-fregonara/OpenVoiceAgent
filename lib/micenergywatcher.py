import threading
import pyaudio
import logging
import time
import struct
from lib.bargecontroller import BargeInController

class MicEnergyWatcher(threading.Thread):
    """
    Simple RMS-based voice activity detection using pyaudio.
    Sets barge_event as soon as sustained voice energy is detected.
    This lets us interrupt AI turn (TTS/LLM) before the utterance is finalized.
    To avoid the mic being triggered by your own TTS output,
    we use a **higher threshold while AI is speaking**. If you’re on open
    speakers and it still self-triggers, set mode="disabled" (see below).
    
    Internal States:
    - ctrl: BargeInController that controls interruptions of ai turn
    - rate: audio rate for pyaudio
    - chunk: chunks size for pyaudio
    - base_thresh: noise threshold
    - sustain_ms: how many milliseconds voice has to be above base_thresh before triggering watcher
    - device_index: device to watch energy for
    - mode: what mode is activated for the energy watcher
        - "high_thresh_while_tts" (default): x4 threshold when AI speaking
        - "always": same threshold always (most sensitive, may self-trigger)
        - "disabled": don't watch mic at all (no instant barge-in; rely on STT)
    - logger: logger to use for debug statements
    """
    def __init__(self, ctrl: BargeInController, rate=16000, chunk=2048,
                 base_thresh=6000, sustain_ms=450, device_index=None, 
                 mode="high_thresh_while_tts", logger=None):
        super().__init__(daemon=True)
        self.ctrl = ctrl
        self.rate = rate
        self.chunk = chunk
        self.base_thresh = base_thresh
        self.sustain_ms = sustain_ms
        self.device_index = device_index
        self.mode = mode
        self._stop = threading.Event()
        self.pa = None
        self.stream = None
        self.log = logger or logging.getLogger(__name__)

    def open(self):
        """Open pyaudio stream to watch audio for."""
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(format=pyaudio.paInt16, channels=1, rate=self.rate,
                                   input=True, frames_per_buffer=self.chunk,
                                   input_device_index=self.device_index)

    def close(self):
        """Close pyaudio stream to watch audio for."""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
        finally:
            self.stream = None
        try:
            if self.pa:
                self.pa.terminate()
        finally:
            self.pa = None

    def _effective_thresh(self):
        """Get the effective threshold based on watcher mode."""
        if self.mode == "disabled":
            return 10**12  # never trigger
        if self.mode == "high_thresh_while_tts" and self.ctrl.ai_speaking.is_set():
            return self.base_thresh * 4  # harder to trigger on your own TTS
        return self.base_thresh

    def run(self):
        """Run the energy watcher, triggering a barge event if voice is detected."""
        if self.mode == "disabled":
            return
        try:
            self.open()
        except Exception as e:
            # If mic can’t open, just disable watcher gracefully.
            self.log.warning(f"MicEnergyWatcher disabled (mic open failed): {e}")
            return

        voiced_ms = 0
        frame_ms = int(1000 * self.chunk / self.rate)
        while not self._stop.is_set():
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                # Compute simple RMS
                n = len(data) // 2
                if n == 0: 
                    time.sleep(0.01); 
                    continue
                samples = struct.unpack("<" + "h"*n, data)
                rms = sum(s*s for s in samples) // n
                thresh = self._effective_thresh()
                if rms > thresh:
                    voiced_ms += frame_ms
                    if voiced_ms >= self.sustain_ms:
                        # print("Exceeded energy in mic watcher!")
                        self.ctrl.barge_event.set()
                        voiced_ms = 0
                else:
                    voiced_ms = max(0, voiced_ms - 2*frame_ms)
            except Exception:
                time.sleep(0.01)
        self.close()

    def stop(self):
        self._stop.set()