# Heather Weather Station

[![CI](https://github.com/Reterics/heather-weather-station/actions/workflows/ci.yml/badge.svg)](https://github.com/Reterics/heather-weather-station/actions/workflows/ci.yml)

A small production service that reads **humidity**, **weather**, **sunlight**, and **terrain height** for a latitude and longitude. One process serves the JSON API and the station dashboard.

Readings are weather-model analyses from [Open-Meteo](https://open-meteo.com/) (CC BY 4.0), not a physical sensor at the coordinate.

```mermaid
flowchart LR
  browser[Dashboard]
  api[Heather API]
  cache[Grid cache]
  upstream[Open-Meteo]
  browser --> api
  api --> cache
  cache -->|miss or refresh| upstream
```

Nearby coordinates share one upstream call. Lookups are snapped to a fixed grid (default 0.01°, about 1.1 km) so slightly different decimals do not bypass the cache. A fresh value is kept for 10 minutes. If Open-Meteo then fails, the last value is still served and marked `stale` for up to 6 hours. The API also rate-limits clients so a crawler cannot turn into an upstream outage.

## Run

Python 3.11 or newer.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m heather
```

Open http://127.0.0.1:8080 for the dashboard and http://127.0.0.1:8080/docs for the API.

```powershell
.\.venv\Scripts\python -m pytest
```

### Docker

```powershell
docker compose up --build
```

The image listens on port 8080 as a non-root user and checks `/health`.

## API

`GET /api/v1/conditions?latitude=47.4979&longitude=19.0402`

| Field | Meaning |
| --- | --- |
| `humidity` | Relative humidity and dew point |
| `weather` | WMO summary, temperature, wind, cloud, rain, pressure |
| `sunlight` | Shortwave radiation, UV, sunshine and daylight today, sunrise and sunset |
| `height` | Terrain elevation above sea level, metres and feet |
| `cache.status` | `miss`, `hit`, or `stale` |
| `location.resolved_*` | Grid point Open-Meteo actually used |

Latitude must be from -90 to 90. Longitude must be from -180 to 180.

`GET /health` is liveness. `GET /ready` is readiness. Conditions responses send `X-RateLimit-Limit` and `X-RateLimit-Remaining`. A limited client gets `429` and `Retry-After`.

## Configuration

Copy `.env.example` to `.env`. Every variable uses the `HEATHER_` prefix.

| Variable | Default | Role |
| --- | --- | --- |
| `HEATHER_GRID_DECIMALS` | `2` | Coordinate snap used as the cache key |
| `HEATHER_CACHE_TTL_SECONDS` | `600` | How long a reading stays fresh |
| `HEATHER_CACHE_STALE_SECONDS` | `21600` | How long a reading may be served after the upstream fails |
| `HEATHER_RATE_LIMIT_PER_MINUTE` | `60` | Per-client limit on `/api/` |
| `HEATHER_OPENMETEO_BASE_URL` | `https://api.open-meteo.com` | Public API, customer API, or a self-hosted Open-Meteo |
| `HEATHER_OPENMETEO_API_KEY` | empty | Server-side key. Never sent to the browser |
| `HEATHER_TRUST_PROXY` | `false` | Trust `X-Forwarded-For` only behind your own proxy |
| `HEATHER_CORS_ORIGINS` | empty | Extra browser origins. Leave empty for the built-in dashboard |

The cache lives in the process. Run one worker, or the limit and the cache will not be shared. The Open-Meteo free tier is for non-commercial use. Commercial use needs their customer API (`HEATHER_OPENMETEO_API_KEY`) or a self-hosted Open-Meteo pointed at with `HEATHER_OPENMETEO_BASE_URL`.

Set `HEATHER_TRUST_PROXY=true` only when a reverse proxy overwrites `X-Forwarded-For`. Otherwise clients can spoof the rate-limit key.
