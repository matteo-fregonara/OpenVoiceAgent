import threading
import queue

class BargeInController:
    """
    Central place for cooperative cancellation and barge-in signaling.

    Internal states:
    - barge_event: set as soon as mic detects user voice activity
    - cancel_event: set when we must abort current AI generation + TTS
    - input_queue: finalized user utterances (strings)
    - ai_speaking: set as soon as ai is speaking (used for cancelling ai speech if user interrupts)
    """
    def __init__(self):
        self.barge_event = threading.Event()
        self.cancel_event = threading.Event()
        self.input_queue = queue.Queue(maxsize=16)
        self.ai_speaking = threading.Event()  # set while AI is speaking/playing

    def request_cancel(self):
        """Signal to cancel the ai turn."""
        self.cancel_event.set()
        self.barge_event.set()  # treat as barge source too

    def reset_for_next_turn(self):
        """Reset for the next ai turn."""
        self.cancel_event.clear()
        self.barge_event.clear()