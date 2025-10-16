import queue
import threading
import uuid
from typing import Generator, List, Any

class BufferStream:
    """
    Class used to store TTS items to say.

    Internal States:
    - _items: queue to store text to say
    - _stop_event: threading event to signal that buffer must be stopped
    """
    def __init__(self):
        self._items: queue.Queue = queue.Queue()
        self._stop_event: threading.Event = threading.Event()

    def add(self, item: Any) -> None:
        """Add an item to the buffer."""
        self._items.put(item)

    def stop(self) -> None:
        """Signal to stop the buffer stream."""
        self._stop_event.set()

    def snapshot(self) -> List[Any]:
        """Take a snapshot of all items in the buffer without exhausting it."""
        with self._items.mutex:
            return list(self._items.queue)

    def gen(self) -> Generator[Any, None, None]:
        """Generate items from the buffer, yielding them one at a time."""
        while not self._stop_event.is_set() or not self._items.empty():
            try:
                yield self._items.get(timeout=0.1)
            except queue.Empty:
                continue


