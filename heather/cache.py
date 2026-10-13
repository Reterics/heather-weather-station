import asyncio
import time
from collections import OrderedDict

from heather.schemas import ConditionsResponse


class ConditionsCache:
    """Process-local TTL cache with a stale window and least-recent eviction.

    Fresh entries are younger than ``ttl_seconds``. Entries younger than
    ``ttl_seconds + stale_seconds`` can still be served when the upstream fails.
    This cache is per process: run one worker, or put a shared cache in front,
    before scaling out.
    """

    def __init__(self, ttl_seconds: int, stale_seconds: int, max_entries: int) -> None:
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, ConditionsResponse]] = OrderedDict()

    def get(self, key: str, now: float | None = None) -> tuple[str, ConditionsResponse] | None:
        now = time.monotonic() if now is None else now
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, value = item
        age = now - stored_at
        if age < self.ttl_seconds:
            self._items.move_to_end(key)
            return "fresh", value
        if age <= self.ttl_seconds + self.stale_seconds:
            return "stale", value
        del self._items[key]
        return None

    def put(self, key: str, value: ConditionsResponse, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._items[key] = (now, value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


class SingleFlight:
    """One in-flight upstream call per cache key."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def lock(self, key: str) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock
