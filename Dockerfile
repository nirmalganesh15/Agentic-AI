# syntax=docker/dockerfile:1

# ---------- 1. Build the Angular UI ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# `npm run build` regenerates the design tokens (prebuild) before the Angular build
RUN npm run build -- --configuration production


# ---------- 2. Python API + models + vector index ----------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    FASTEMBED_CACHE_PATH=/app/models \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    PYTHONUNBUFFERED=1

# Run as a non-root user; everything below is created by and owned by it
RUN useradd --create-home --uid 1000 app && mkdir /app && chown app:app /app
USER app
WORKDIR /app

# Dependencies first, so this layer stays cached until pyproject.toml or uv.lock change
COPY --chown=app:app pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=app:app src/ src/
RUN uv sync --frozen --no-dev

COPY --chown=app:app resources/ resources/
COPY --chown=app:app evals/ evals/
COPY --chown=app:app --from=frontend /frontend/dist/frontend/browser frontend/dist/frontend/browser

# Build the vector index and download all models at build time: the image is a
# self-contained, immutable artifact and startup needs no network or ingestion.
RUN .venv/bin/python -m rag.ingest --recreate \
 && .venv/bin/python -c "from rag.vector_store import get_client, warm_up; warm_up(); get_client().close()"

# Render injects PORT; FORWARDED_ALLOW_IPS lets uvicorn read the real client IP from the proxy
ENV HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    FORWARDED_ALLOW_IPS=*
EXPOSE 8000

CMD [".venv/bin/rag-server"]
