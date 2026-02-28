"""
Token bucket rate limiter. Used for Brave API and web fetching.
"""

import time
import threading


class RateLimiter:
    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            wait_time = self.min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_call = time.monotonic()


# Shared instances — pipeline code imports these directly
brave_limiter = RateLimiter(calls_per_minute=20)    # Reserve 10 for OpenClaw
web_limiter = RateLimiter(calls_per_minute=12)       # ~1 req/5s per domain (managed per-domain in base collector)
