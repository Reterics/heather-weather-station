import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-memory per-key limiter. Enough for one process behind a reverse proxy."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, int, int]:
        """Return allowed, remaining, and seconds until the oldest hit leaves the window."""
        if self.limit <= 0:
            return True, 0, 0
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = max(1, int(hits[0] + self.window_seconds - now) + 1)
            return False, 0, retry_after
        hits.append(now)
        remaining = self.limit - len(hits)
        return True, remaining, self.window_seconds
