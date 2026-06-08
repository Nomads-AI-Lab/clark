FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JKG_ENV=production \
    JKG_DB_PATH=/data/memory_v3.db \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN addgroup --system jkg && adduser --system --ingroup jkg jkg

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY jkg ./jkg

RUN uv sync --extra server --frozen --no-dev

RUN mkdir -p /data && chown -R jkg:jkg /data /app

USER jkg

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["jkg", "serve", "8000"]
