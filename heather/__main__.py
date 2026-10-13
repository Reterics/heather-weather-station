import uvicorn

from heather.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "heather.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=settings.trust_proxy,
        forwarded_allow_ips="*" if settings.trust_proxy else None,
    )


if __name__ == "__main__":
    main()
