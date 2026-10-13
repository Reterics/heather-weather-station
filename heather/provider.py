import asyncio
import logging
import math
from decimal import Decimal, ROUND_HALF_UP

import httpx

from heather.codes import sunlight_description, weather_summary
from heather.config import Settings
from heather.schemas import (
    ConditionsResponse,
    Height,
    Humidity,
    Location,
    Source,
    Sunlight,
    Weather,
)

log = logging.getLogger("heather.provider")

CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "dew_point_2m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "uv_index",
    "sunshine_duration",
)
DAILY_FIELDS = (
    "sunrise",
    "sunset",
    "sunshine_duration",
    "daylight_duration",
    "uv_index_max",
)
ATTRIBUTION = (
    "Weather data by Open-Meteo.com, CC BY 4.0. "
    "Model output is selected per location from services such as DWD, NOAA, and ECMWF."
)
METERS_TO_FEET = 3.280839895


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def snap_coordinate(value: float, decimals: int) -> float:
    quantum = Decimal(1).scaleb(-decimals)
    snapped = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(snapped)


def _number(data: dict, key: str) -> float | None:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _first(daily: dict, key: str):
    values = daily.get(key) or []
    if not values:
        return None
    return values[0]


def _with_offset(naive: str | None, offset_seconds: int | None) -> str | None:
    if not naive or offset_seconds is None:
        return naive
    if len(naive) == 16:
        naive = f"{naive}:00"
    sign = "+" if offset_seconds >= 0 else "-"
    hours, minutes = divmod(abs(int(offset_seconds)) // 60, 60)
    return f"{naive}{sign}{hours:02d}:{minutes:02d}"


class OpenMeteoProvider:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def fetch(self, latitude: float, longitude: float) -> ConditionsResponse:
        snapped_lat = snap_coordinate(latitude, self._settings.grid_decimals)
        snapped_lon = snap_coordinate(longitude, self._settings.grid_decimals)
        payload = await self._get_forecast(snapped_lat, snapped_lon)
        return self._parse(payload, latitude, longitude)

    async def _get_forecast(self, latitude: float, longitude: float) -> dict:
        url = self._settings.openmeteo_base_url.rstrip("/") + "/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(CURRENT_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "forecast_days": 1,
            "timezone": "auto",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
        if self._settings.openmeteo_api_key:
            params["apikey"] = self._settings.openmeteo_api_key

        attempts = self._settings.upstream_retries + 1
        last_error = UpstreamError("Weather service is temporarily unavailable.")
        for attempt in range(attempts):
            response: httpx.Response | None = None
            try:
                response = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_error = UpstreamError("Weather service did not respond in time.")
                log.warning("upstream_transport_error attempt=%s error=%s", attempt + 1, type(exc).__name__)
            else:
                if response.status_code == 200:
                    return self._decode(response)
                retryable = response.status_code == 429 or response.status_code >= 500
                last_error = UpstreamError(
                    "Weather service is temporarily unavailable."
                    if retryable
                    else "Weather service rejected the request.",
                    status_code=response.status_code,
                )
                log.warning("upstream_http_error attempt=%s status=%s", attempt + 1, response.status_code)
                if not retryable:
                    raise last_error

            if attempt + 1 < attempts:
                await asyncio.sleep(self._retry_delay(response))

        raise last_error

    def _decode(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise UpstreamError("Weather service returned an unreadable response.") from exc
        if not isinstance(body, dict):
            raise UpstreamError("Weather service returned an unexpected response.")
        return body

    def _retry_delay(self, response: httpx.Response | None) -> float:
        if response is not None:
            header = response.headers.get("Retry-After")
            if header and header.isdigit():
                return min(float(header), 2.0)
        return self._settings.retry_backoff_seconds

    def _parse(self, payload: dict, latitude: float, longitude: float) -> ConditionsResponse:
        current = payload.get("current")
        if not isinstance(current, dict):
            raise UpstreamError("Weather service omitted current conditions.")

        daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
        offset = payload.get("utc_offset_seconds")
        offset_seconds = int(offset) if isinstance(offset, int) else None
        is_day_raw = current.get("is_day")
        is_day = None if is_day_raw is None else bool(is_day_raw)
        code_raw = current.get("weather_code")
        code = int(code_raw) if isinstance(code_raw, int) else None
        elevation = payload.get("elevation")
        elevation_m = float(elevation) if isinstance(elevation, (int, float)) and math.isfinite(elevation) else None
        shortwave = _number(current, "shortwave_radiation")
        resolved_lat = payload.get("latitude")
        resolved_lon = payload.get("longitude")

        return ConditionsResponse(
            location=Location(
                latitude=latitude,
                longitude=longitude,
                resolved_latitude=float(resolved_lat) if isinstance(resolved_lat, (int, float)) else latitude,
                resolved_longitude=float(resolved_lon) if isinstance(resolved_lon, (int, float)) else longitude,
                timezone=payload.get("timezone") if isinstance(payload.get("timezone"), str) else None,
                utc_offset_seconds=offset_seconds,
            ),
            observed_at=_with_offset(current.get("time") if isinstance(current.get("time"), str) else None, offset_seconds),
            humidity=Humidity(
                relative_percent=_number(current, "relative_humidity_2m"),
                dew_point_c=_number(current, "dew_point_2m"),
            ),
            weather=Weather(
                code=code,
                summary=weather_summary(code),
                temperature_c=_number(current, "temperature_2m"),
                apparent_temperature_c=_number(current, "apparent_temperature"),
                precipitation_mm=_number(current, "precipitation"),
                cloud_cover_percent=_number(current, "cloud_cover"),
                pressure_hpa=_number(current, "pressure_msl"),
                wind_speed_kmh=_number(current, "wind_speed_10m"),
                wind_direction_deg=_number(current, "wind_direction_10m"),
                wind_gusts_kmh=_number(current, "wind_gusts_10m"),
                is_day=is_day,
            ),
            sunlight=Sunlight(
                shortwave_radiation_wm2=shortwave,
                direct_radiation_wm2=_number(current, "direct_radiation"),
                diffuse_radiation_wm2=_number(current, "diffuse_radiation"),
                uv_index=_number(current, "uv_index"),
                uv_index_max_today=_number_or_none(_first(daily, "uv_index_max")),
                sunshine_duration_today_s=_number_or_none(_first(daily, "sunshine_duration")),
                daylight_duration_s=_number_or_none(_first(daily, "daylight_duration")),
                sunrise=_with_offset(_string_or_none(_first(daily, "sunrise")), offset_seconds),
                sunset=_with_offset(_string_or_none(_first(daily, "sunset")), offset_seconds),
                is_day=is_day,
                description=sunlight_description(is_day, shortwave),
            ),
            height=Height(
                elevation_m=elevation_m,
                elevation_ft=None if elevation_m is None else round(elevation_m * METERS_TO_FEET, 1),
            ),
            source=Source(attribution=ATTRIBUTION),
            cache={"status": "miss", "ttl_seconds": self._settings.cache_ttl_seconds},
        )


def _string_or_none(value) -> str | None:
    return value if isinstance(value, str) else None


def _number_or_none(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)
