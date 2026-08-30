"""
In-memory fixed-window rate limiting for sensitive endpoints.

Deliberately simple and single-process (the deployed backend runs one
uvicorn worker per container). Sits on login, public apply, and invite
validation — the three places an anonymous client can drive the server.

Each sensitive route uses its own named bucket so a burst on one endpoint
(e.g. brute-forcing login) cannot exhaust the budget of another (e.g.
applying to a job) — they were shared behind one default bucket before.
"""
import time
import threading
from collections import defaultdict

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 10

_events: dict = defaultdict(list)
_lock = threading.Lock()


def _check(key: str):
    now = time.time()
    with _lock:
        recent = [t for t in _events[key] if now - t < _WINDOW_SECONDS]
        if len(recent) >= _MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
            )
        recent.append(now)
        _events[key] = recent


def rate_limited(bucket: str):
    """Return a FastAPI dependency enforcing a per-bucket, per-IP limit."""
    def _dependency(request: Request):
        host = request.client.host if request.client else "unknown"
        _check(f"{bucket}:{host}")
    return _dependency


def reset_rate_limits():
    """Test hook — clears all counted events."""
    with _lock:
        _events.clear()