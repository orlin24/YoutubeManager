"""Simple in-memory sliding-window rate limiter (per IP + route)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import Request

from app.config import get_settings
from app.utils.errors import AppError

_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LOCK = Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(limit: int, window_seconds: int) -> Callable:
    """Returns a FastAPI dependency enforcing limit/window per (ip, route)."""

    def dependency(request: Request) -> None:
        if get_settings().APP_ENV == "test":
            return  # rate limits disabled in the test suite
        key = (_client_ip(request), request.url.path)
        now = time.monotonic()
        with _LOCK:
            bucket = _BUCKETS[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                raise AppError(429, "RATE_LIMITED", "Too many requests. Please try again later.")
            bucket.append(now)

    return dependency
