"""Small in-memory, per-IP sliding-window rate limiter for public endpoints (no extra dependency)."""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_ALL: list["RateLimiter"] = []


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int, name: str) -> None:
        self.limit = limit
        self.window = window_seconds
        self.name = name
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        _ALL.append(self)

    def __call__(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            hits = self._hits[ip]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def reset_all() -> None:
    for limiter in _ALL:
        limiter.reset()


ticket_submit_limit = RateLimiter(10, 60, "ticket-submit")
public_read_limit = RateLimiter(120, 60, "public-read")
login_limit = RateLimiter(20, 60, "login")
token_respond_limit = RateLimiter(20, 60, "token-respond")
