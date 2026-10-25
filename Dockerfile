# Production image: gunicorn serving the Flask app. Builds with docker or podman
# (use `podman build --format docker` to keep the HEALTHCHECK).

FROM ghcr.io/astral-sh/uv:0.13.5-python3.13-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Dependencies first, so source edits don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable
COPY LICENSE README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Same CPython patch release as the builder image (check with
# `podman run --rm <builder image> python -V`); bump both tags together.
FROM python:3.13.16-slim-trixie
RUN useradd --system --uid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin spoolmaker
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    TRUST_PROXY=1 \
    PORT=8000 \
    WEB_CONCURRENCY=2
USER 10001
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=4)"]
CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers "${WEB_CONCURRENCY}" --threads 4 \
    --timeout 60 --no-control-socket --access-logfile - "spoolmaker.app:create_app()"
