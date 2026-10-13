import httpx
from pydantic_settings import SettingsConfigDict

from heather.config import Settings

FORECAST = {
    "latitude": 47.501236,
    "longitude": 19.03534,
    "utc_offset_seconds": 7200,
    "timezone": "Europe/Budapest",
    "elevation": 113.0,
    "current": {
        "time": "2026-10-13T20:45",
        "temperature_2m": 11.7,
        "relative_humidity_2m": 45,
        "apparent_temperature": 9.0,
        "is_day": 0,
        "precipitation": 0.0,
        "weather_code": 0,
        "cloud_cover": 0,
        "pressure_msl": 1026.3,
        "wind_speed_10m": 4.7,
        "wind_direction_10m": 295,
        "wind_gusts_10m": 6.5,
        "dew_point_2m": 0.2,
        "shortwave_radiation": 0.0,
        "direct_radiation": 0.0,
        "diffuse_radiation": 0.0,
        "uv_index": 0.0,
        "sunshine_duration": 0.0,
    },
    "daily": {
        "sunrise": ["2026-10-13T06:59"],
        "sunset": ["2026-10-13T18:00"],
        "sunshine_duration": [35437.70],
        "daylight_duration": [39655.61],
        "uv_index_max": [3.45],
    },
}


def make_settings(**overrides) -> Settings:
    class Isolated(Settings):
        model_config = SettingsConfigDict(
            env_prefix="HEATHER_ISOLATED_",
            env_file=None,
            extra="ignore",
        )

    return Isolated(**overrides)


def scripted_transport(responses: list[httpx.Response]):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        index = min(len(calls) - 1, len(responses) - 1)
        return responses[index]

    return calls, httpx.MockTransport(handler)
