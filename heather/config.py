from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field maps to HEATHER_<NAME>."""

    model_config = SettingsConfigDict(
        env_prefix="HEATHER_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    # Weather models are kilometre-scale. Snapping lookups onto a fixed grid
    # keeps one upstream call shared by nearby requests. Two decimals is ~1.1 km.
    grid_decimals: int = Field(default=2, ge=0, le=5)
    cache_ttl_seconds: int = Field(default=600, ge=0)
    cache_stale_seconds: int = Field(default=6 * 3600, ge=0)
    cache_max_entries: int = Field(default=2_000, ge=1)

    upstream_timeout_seconds: float = Field(default=8.0, gt=0)
    upstream_retries: int = Field(default=1, ge=0, le=3)
    retry_backoff_seconds: float = Field(default=0.4, ge=0)

    # 0 disables the limiter (tests). Production default is 60/minute per client.
    rate_limit_per_minute: int = Field(default=60, ge=0)
    trust_proxy: bool = False

    openmeteo_base_url: str = "https://api.open-meteo.com"
    openmeteo_api_key: str | None = None

    # Comma-separated browser origins. Empty keeps the API same-origin only.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]
