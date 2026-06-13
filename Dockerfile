FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLARK_ENV=production \
    CLARK_DB_PATH=/data/memory_v3.db \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN addgroup --system clark && adduser --system --ingroup clark clark

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY clark ./clark

RUN uv sync --extra server --frozen --no-dev

RUN mkdir -p /data && chown -R clark:clark /data /app

USER clark

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["clark", "serve", "8000"]
