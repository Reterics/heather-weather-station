FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 heather

COPY pyproject.toml README.md ./
COPY heather ./heather
COPY static ./static

RUN pip install --no-cache-dir .

USER heather

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"]

CMD ["python", "-m", "heather"]
