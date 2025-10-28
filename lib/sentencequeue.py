import threading
from typing import Optional
import uuid

class Sentence:
    """
    Singular sentence for the TTS handler.
    """
    def __init__(self, emotion: Optional[str] = None):
        self.text = ""
        self.emotion = emotion
        self.is_finished = False
        self.retrieved = False
        self.popped = False
        self.lock = threading.Lock()
        self.id: str = str(uuid.uuid4())

    def add_text(self, text: str):
        with self.lock:
            self.text += text

    def get_text(self):
        with self.lock:
            return self.text

    def mark_finished(self):
        with self.lock:
            self.is_finished = True

    def get_finished(self):
        with self.lock:
            return self.is_finished

    def __str__(self):
        with self.lock:
            return f"Sentence(text='{self.text}', emotion='{self.emotion}', is_finished={self.is_finished})"

class ThreadSafeSentenceQueue:
    """
    Sentence queue for the TTS handler before it gets played.

    Internal States:
    - queue: queue of Sentence objects to be played.
    - current_sentence: current sentence to be played
    - lock: lock for the sentence queue
    """
    def __init__(self):
        self.queue = []
        self.current_sentence = None
        self.lock = threading.Lock()

    def finish_current_sentence(self):
        """Put the current sentence on the to be played queue."""
        with self.lock:
            if self.current_sentence and not self.current_sentence.is_finished:
                self.current_sentence.mark_finished()
                if not self.current_sentence.retrieved:
                    self.queue.append(self.current_sentence)
                self.current_sentence = None

    def add_emotion(self, emotion: str):
        """Finish the current sentence by adding it to the queue, create a new sentence with a new emotion."""
        with self.lock:
            if self.current_sentence and self.current_sentence.get_text():
                self.current_sentence.mark_finished()
                if not self.current_sentence.retrieved:
                    self.queue.append(self.current_sentence)
            self.current_sentence = Sentence(emotion)

    def add_text(self, text: str):
        """Add text to the current sentence if it doesn't already have text."""
        with self.lock:
            if not text.strip():
                if not self.current_sentence:
                    return
                if not self.current_sentence.get_text():
                    return

            if not self.current_sentence:
                self.current_sentence = Sentence()
            
            self.current_sentence.add_text(text)

    def get_sentence(self) -> Optional[Sentence]:
        """Get the next sentence to be played."""
        with self.lock:
            if self.queue:
                sentence = self.queue.pop(0)
                sentence.popped = True
                return sentence
            elif self.current_sentence:
                self.current_sentence.retrieved = True
                return self.current_sentence
            else:
                return None

    def is_empty(self) -> bool:
        """Returns whether the current queue is empty."""
        with self.lock:
            return len(self.queue) == 0

    def __len__(self):
        """Returns length of current queue."""
        with self.lock:
            return len(self.queue)