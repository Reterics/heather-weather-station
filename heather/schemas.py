from typing import Literal

from pydantic import BaseModel


class Humidity(BaseModel):
    relative_percent: float | None = None
    dew_point_c: float | None = None


class Weather(BaseModel):
    code: int | None = None
    summary: str
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    precipitation_mm: float | None = None
    cloud_cover_percent: float | None = None
    pressure_hpa: float | None = None
    wind_speed_kmh: float | None = None
    wind_direction_deg: float | None = None
    wind_gusts_kmh: float | None = None
    is_day: bool | None = None


class Sunlight(BaseModel):
    shortwave_radiation_wm2: float | None = None
    direct_radiation_wm2: float | None = None
    diffuse_radiation_wm2: float | None = None
    uv_index: float | None = None
    uv_index_max_today: float | None = None
    sunshine_duration_today_s: float | None = None
    daylight_duration_s: float | None = None
    sunrise: str | None = None
    sunset: str | None = None
    is_day: bool | None = None
    description: str


class Height(BaseModel):
    elevation_m: float | None = None
    elevation_ft: float | None = None


class Location(BaseModel):
    latitude: float
    longitude: float
    resolved_latitude: float
    resolved_longitude: float
    timezone: str | None = None
    utc_offset_seconds: int | None = None


class CacheInfo(BaseModel):
    status: Literal["hit", "miss", "stale"]
    ttl_seconds: int


class Source(BaseModel):
    provider: str = "open-meteo"
    license: str = "CC BY 4.0"
    attribution: str


class ConditionsResponse(BaseModel):
    location: Location
    observed_at: str | None = None
    humidity: Humidity
    weather: Weather
    sunlight: Sunlight
    height: Height
    source: Source
    cache: CacheInfo


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail


class HealthBody(BaseModel):
    status: Literal["ok"] = "ok"
