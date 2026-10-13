import asyncio

import httpx
from fastapi.testclient import TestClient

from heather.app import create_app
from heather.cache import ConditionsCache
from heather.codes import sunlight_description, weather_summary
from heather.provider import OpenMeteoProvider, snap_coordinate
from heather.service import ConditionsService
from tests.conftest import FORECAST, make_settings, scripted_transport


def client_for(responses, **settings):
    _calls, transport = scripted_transport(responses)
    app = create_app(make_settings(**settings), transport=transport)
    return _calls, TestClient(app)


def test_conditions_maps_humidity_weather_sunlight_and_height():
    calls, client = client_for([httpx.Response(200, json=FORECAST)], openmeteo_api_key="secret")
    with client:
        response = client.get("/api/v1/conditions", params={"latitude": 47.4979, "longitude": 19.0402})
    assert response.status_code == 200
    body = response.json()
    assert body["humidity"]["relative_percent"] == 45
    assert body["humidity"]["dew_point_c"] == 0.2
    assert body["weather"]["summary"] == "Clear sky"
    assert body["weather"]["temperature_c"] == 11.7
    assert body["weather"]["is_day"] is False
    assert body["sunlight"]["description"] == "Night"
    assert body["sunlight"]["shortwave_radiation_wm2"] == 0
    assert body["sunlight"]["uv_index_max_today"] == 3.45
    assert body["sunlight"]["sunrise"] == "2026-10-13T06:59:00+02:00"
    assert body["height"]["elevation_m"] == 113
    assert body["height"]["elevation_ft"] == 370.7
    assert body["observed_at"] == "2026-10-13T20:45:00+02:00"
    assert body["location"]["resolved_latitude"] == 47.501236
    assert body["cache"]["status"] == "miss"
    assert body["source"]["license"] == "CC BY 4.0"
    sent = calls[0].url.params
    assert float(sent["latitude"]) == 47.5
    assert float(sent["longitude"]) == 19.04
    assert sent["apikey"] == "secret"
    assert "secret" not in response.text


def test_second_lookup_on_the_same_grid_is_a_cache_hit():
    calls, client = client_for([httpx.Response(200, json=FORECAST)])
    with client:
        first = client.get("/api/v1/conditions", params={"latitude": 47.4979, "longitude": 19.0402})
        second = client.get("/api/v1/conditions", params={"latitude": 47.496, "longitude": 19.041})
    assert first.json()["cache"]["status"] == "miss"
    assert second.json()["cache"]["status"] == "hit"
    assert len(calls) == 1


def test_upstream_failure_serves_stale_then_errors_when_empty():
    calls, client = client_for(
        [
            httpx.Response(200, json=FORECAST),
            httpx.Response(503, json={"error": True}),
        ],
        cache_ttl_seconds=0,
        upstream_retries=0,
    )
    with client:
        warm = client.get("/api/v1/conditions", params={"latitude": 10, "longitude": 10})
        stale = client.get("/api/v1/conditions", params={"latitude": 10, "longitude": 10})
    assert warm.status_code == 200
    assert stale.status_code == 200
    assert stale.json()["cache"]["status"] == "stale"
    assert len(calls) == 2

    _calls, cold = client_for([httpx.Response(500)], upstream_retries=0)
    with cold:
        failed = cold.get("/api/v1/conditions", params={"latitude": 10, "longitude": 10})
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "upstream_unavailable"


def test_retries_a_rate_limited_upstream_once():
    calls, client = client_for(
        [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=FORECAST),
        ],
        retry_backoff_seconds=0,
    )
    with client:
        response = client.get("/api/v1/conditions", params={"latitude": 1, "longitude": 1})
    assert response.status_code == 200
    assert len(calls) == 2


def test_rejects_coordinates_outside_range():
    _calls, client = client_for([httpx.Response(200, json=FORECAST)])
    with client:
        response = client.get("/api/v1/conditions", params={"latitude": 91, "longitude": 0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_coordinates"
    assert _calls == []


def test_rate_limit_headers_and_retry_after():
    _calls, client = client_for(
        [httpx.Response(200, json=FORECAST)],
        rate_limit_per_minute=2,
    )
    with client:
        assert client.get("/api/v1/conditions", params={"latitude": 1, "longitude": 2}).status_code == 200
        assert client.get("/api/v1/conditions", params={"latitude": 1, "longitude": 2}).status_code == 200
        blocked = client.get("/api/v1/conditions", params={"latitude": 1, "longitude": 2})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


def test_health_ready_and_dashboard():
    _calls, client = client_for([httpx.Response(200, json=FORECAST)])
    with client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ok"}
        page = client.get("/")
        assert page.status_code == 200
        assert "Read conditions" in page.text
        assert "Humidity" in page.text
        script = client.get("/app.js")
        style = client.get("/styles.css")
    assert script.status_code == 200
    assert "readConditions" in script.text
    assert style.status_code == 200


def test_snap_uses_half_up_on_the_weather_grid():
    assert snap_coordinate(47.4979, 2) == 47.5
    assert snap_coordinate(-21.9426, 2) == -21.94
    assert weather_summary(95) == "Thunderstorm"
    assert weather_summary(None) == "Unavailable"
    assert sunlight_description(True, 900) == "Intense"
    assert sunlight_description(False, 900) == "Night"


def test_concurrent_lookups_share_one_upstream_call():
    calls = {"n": 0}

    async def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=FORECAST)

    async def scenario():
        settings = make_settings()
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            service = ConditionsService(
                OpenMeteoProvider(http, settings),
                ConditionsCache(600, 3600, 100),
                settings,
            )
            first, second = await asyncio.gather(
                service.get(47.4979, 19.0402),
                service.get(47.4961, 19.041),
            )
        assert calls["n"] == 1
        assert {first.cache.status, second.cache.status} == {"hit", "miss"}

    asyncio.run(scenario())
