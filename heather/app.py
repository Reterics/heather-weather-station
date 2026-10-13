import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from heather import __version__
from heather.cache import ConditionsCache
from heather.config import Settings
from heather.limiter import SlidingWindowLimiter
from heather.provider import OpenMeteoProvider, UpstreamError
from heather.schemas import ConditionsResponse, ErrorBody, ErrorDetail, HealthBody
from heather.service import ConditionsService

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("heather.http")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(getattr(handler, "_heather", False) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler._heather = True  # type: ignore[attr-defined]
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)


def client_address(request: Request, settings: Settings) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        timeout = httpx.Timeout(settings.upstream_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            provider = OpenMeteoProvider(client, settings)
            cache = ConditionsCache(
                ttl_seconds=settings.cache_ttl_seconds,
                stale_seconds=settings.cache_stale_seconds,
                max_entries=settings.cache_max_entries,
            )
            app.state.service = ConditionsService(provider, cache, settings)
            app.state.ready = True
            yield
        app.state.ready = False

    app = FastAPI(
        title="Heather Weather Station",
        version=__version__,
        summary="Humidity, weather, sunlight, and terrain height for a geographic point.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.ready = False
    app.state.limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_and_limit(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        limited = request.url.path.startswith("/api/")
        allowed, remaining, retry_after = True, settings.rate_limit_per_minute, 0
        if limited:
            allowed, remaining, retry_after = app.state.limiter.check(client_address(request, settings))
        if not allowed:
            body = ErrorBody(
                error=ErrorDetail(
                    code="rate_limited",
                    message="Too many requests. Wait and try this coordinate again.",
                )
            )
            response = JSONResponse(status_code=429, content=body.model_dump())
            response.headers["Retry-After"] = str(retry_after)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path not in {"/docs", "/redoc", "/openapi.json"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                "script-src 'self'; connect-src 'self'; base-uri 'self'; "
                "form-action 'self'; frame-ancestors 'none'"
            )
        if limited:
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        log.info(
            "request id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.get("/health", response_model=HealthBody, tags=["ops"])
    async def health() -> HealthBody:
        return HealthBody()

    @app.get("/ready", response_model=HealthBody, tags=["ops"])
    async def ready() -> HealthBody:
        if not app.state.ready:
            return JSONResponse(
                status_code=503,
                content=ErrorBody(
                    error=ErrorDetail(code="not_ready", message="The station is still starting.")
                ).model_dump(),
            )
        return HealthBody()

    @app.get(
        "/api/v1/conditions",
        response_model=ConditionsResponse,
        tags=["conditions"],
        responses={429: {"model": ErrorBody}, 503: {"model": ErrorBody}},
    )
    async def conditions(
        latitude: float = Query(..., ge=-90, le=90),
        longitude: float = Query(..., ge=-180, le=180),
    ) -> ConditionsResponse:
        try:
            return await app.state.service.get(latitude, longitude)
        except UpstreamError as exc:
            log.warning("upstream_unavailable status=%s", exc.status_code)
            return JSONResponse(
                status_code=503,
                content=ErrorBody(
                    error=ErrorDetail(code="upstream_unavailable", message=str(exc))
                ).model_dump(),
            )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        friendly = {
            "latitude": "Latitude must be a number from -90 to 90.",
            "longitude": "Longitude must be a number from -180 to 180.",
        }
        parts: list[str] = []
        for item in exc.errors():
            fields = [str(piece) for piece in item.get("loc", []) if piece != "query"]
            field = fields[-1] if fields else ""
            text = friendly.get(field)
            if text is None:
                loc = ".".join(fields)
                text = f"{loc}: {item.get('msg', 'invalid')}" if loc else item.get("msg", "invalid")
            if text not in parts:
                parts.append(text)
        message = " ".join(parts) or "Invalid coordinates."
        body = ErrorBody(error=ErrorDetail(code="invalid_coordinates", message=message))
        return JSONResponse(status_code=422, content=body.model_dump())

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

    return app
