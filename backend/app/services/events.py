"""In-memory publish/subscribe feeding the Server-Sent Events streams.

Publishing is thread-safe: request handlers run in a thread pool and the scheduler in its own
thread, while subscribers live on the asyncio event loop. Always publish *after* db.commit()."""
import asyncio
import threading
from collections import deque
from typing import Optional

CHANNELS = ("tickets", "logs", "adjustments")


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.recent: deque = deque(maxlen=200)  # for tests and debugging

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subs.setdefault(channel, set()).add(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subs.get(channel, set()).discard(queue)

    def publish(self, channel: str, event_type: str, data: dict) -> None:
        message = {"channel": channel, "type": event_type, "data": data}
        self.recent.append(message)
        with self._lock:
            queues = list(self._subs.get(channel, ()))
        loop = self._loop
        if not queues or loop is None or loop.is_closed():
            return
        for queue in queues:
            loop.call_soon_threadsafe(_put, queue, message)


def _put(queue: asyncio.Queue, message: dict) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        pass  # a stuck client misses events; it refetches on reconnect


broker = Broker()
