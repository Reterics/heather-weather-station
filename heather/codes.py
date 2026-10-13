"""WMO weather interpretation codes used by Open-Meteo."""

WMO_SUMMARY: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Slight rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Slight snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def weather_summary(code: int | None) -> str:
    if code is None:
        return "Unavailable"
    return WMO_SUMMARY.get(code, "Unknown conditions")


def sunlight_description(is_day: bool | None, shortwave_wm2: float | None) -> str:
    if is_day is False:
        return "Night"
    if shortwave_wm2 is None:
        return "Unavailable"
    if shortwave_wm2 < 20:
        return "Dark"
    if shortwave_wm2 < 100:
        return "Dim"
    if shortwave_wm2 < 300:
        return "Soft"
    if shortwave_wm2 < 600:
        return "Bright"
    if shortwave_wm2 < 850:
        return "Strong"
    return "Intense"
