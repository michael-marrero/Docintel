# syntax=docker/dockerfile:1.7
#
# docintel — multi-target Dockerfile.
#
# Build:
#   docker build --target api -t docintel-api:test --build-arg GIT_SHA=$(git rev-parse HEAD) -f docker/Dockerfile .
#   docker build --target ui  -t docintel-ui:test  --build-arg GIT_SHA=$(git rev-parse HEAD) -f docker/Dockerfile .
#
# CONTEXT.md D-05 / D-06 / D-08 / D-09: single Dockerfile, BGE pre-warm in `api` only,
# image-size cap < 3 GiB enforced by CI, git_sha injected via ARG.

# ============================================================================
# Stage: base — system deps + Python runtime + uv + workspace install (no apps)
# ============================================================================
FROM python:3.11-slim-bookworm AS base

ARG GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/root/.cache/uv \
    HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache \
    PATH="/opt/venv/bin:$PATH" \
    DOCINTEL_LLM_PROVIDER=stub \
    DOCINTEL_GIT_SHA=${GIT_SHA}

# System dependencies required by the unstructured / OCR / table parsers.
# (Tesseract MUST be on PATH — never hardcode the binary path. PITFALLS.md #27.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        poppler-utils \
        tesseract-ocr \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (single static binary, ~15 MB).
COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace metadata first to maximize Docker layer cache reuse.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/docintel-core/pyproject.toml      packages/docintel-core/pyproject.toml
COPY packages/docintel-api/pyproject.toml       packages/docintel-api/pyproject.toml
COPY packages/docintel-ui/pyproject.toml        packages/docintel-ui/pyproject.toml
COPY packages/docintel-eval/pyproject.toml      packages/docintel-eval/pyproject.toml

# Sync the shared package only; per-target stages add their own.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package docintel-core

# Copy source last (changes most often).
COPY packages/ packages/

# ============================================================================
# Stage: api — FastAPI service + BGE reranker pre-warm
# ============================================================================
FROM base AS api

# Install api package + its deps (FastAPI, uvicorn, sentence-transformers).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package docintel-api

# Pre-warm bge-reranker-base into HF_HOME=/opt/hf-cache so /health on a
# no-network reviewer machine works on the first call.
# (Phase 5 will actually invoke the reranker; Phase 1 just bakes the layer.)
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "docintel_api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ============================================================================
# Stage: ui — Streamlit UI (slim, no ML weights)
# ============================================================================
FROM base AS ui

# Install ui package + its deps (Streamlit, httpx). NO sentence-transformers
# in the ui image — keeps it well under 1 GiB.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package docintel-ui

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", \
     "/app/packages/docintel-ui/src/docintel_ui/streamlit_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
