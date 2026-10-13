import logging
import time

from heather.cache import ConditionsCache, SingleFlight
from heather.config import Settings
from heather.provider import OpenMeteoProvider, UpstreamError, snap_coordinate
from heather.schemas import CacheInfo, ConditionsResponse

log = logging.getLogger("heather.service")


class ConditionsService:
    def __init__(self, provider: OpenMeteoProvider, cache: ConditionsCache, settings: Settings) -> None:
        self._provider = provider
        self._cache = cache
        self._settings = settings
        self._flight = SingleFlight()

    async def get(self, latitude: float, longitude: float) -> ConditionsResponse:
        key = self._key(latitude, longitude)
        cached = self._cache.get(key)
        if cached and cached[0] == "fresh":
            return self._mark(cached[1], "hit")

        async with await self._flight.lock(key):
            cached = self._cache.get(key)
            if cached and cached[0] == "fresh":
                return self._mark(cached[1], "hit")
            try:
                fresh = await self._provider.fetch(latitude, longitude)
            except UpstreamError:
                cached = self._cache.get(key)
                if cached is not None:
                    log.warning("serving_stale key=%s", key)
                    return self._mark(cached[1], "stale")
                raise
            self._cache.put(key, fresh, time.monotonic())
            return self._mark(fresh, "miss")

    def _key(self, latitude: float, longitude: float) -> str:
        decimals = self._settings.grid_decimals
        return f"{snap_coordinate(latitude, decimals):.{decimals}f},{snap_coordinate(longitude, decimals):.{decimals}f}"

    def _mark(self, conditions: ConditionsResponse, status: str) -> ConditionsResponse:
        return conditions.model_copy(
            update={"cache": CacheInfo(status=status, ttl_seconds=self._settings.cache_ttl_seconds)}
        )
