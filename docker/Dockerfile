# syntax=docker/dockerfile:1.7
#
# docintel — Dockerfile for the api service (serves the static web/ workspace).
#
# Build:
#   docker build --target api -t docintel-api:test --build-arg GIT_SHA=$(git rev-parse HEAD) -f docker/Dockerfile .
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

# System dependencies required by the unstructured / OCR / table parsers
# (Tesseract MUST be on PATH — never hardcode the binary path. PITFALLS.md #27)
# AND build tools required to compile the `pystemmer` sdist (no wheels on
# PyPI as of v3.0.0; transitively pulled by `docintel-index` via bm25s).
# `build-essential` is gcc + g++ + make + libc6-dev (~260 MB) — needed only at
# image-build time, but kept in the base layer because both api and ui stages
# inherit `base` and removing them in a later layer wouldn't shrink the
# resulting image (Docker layers are union-mount, not differential). If the
# image-size cap (< 3 GiB, per Dockerfile preamble) is breached, refactor to
# a dedicated builder stage that compiles wheels then copies them to a clean
# runtime stage. For the stub-mode demo image this is acceptable headroom.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        poppler-utils \
        tesseract-ocr \
        ca-certificates \
        curl \
        build-essential \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (single static binary, ~15 MB).
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

WORKDIR /app

# Copy workspace metadata first to maximize Docker layer cache reuse.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/docintel-core/pyproject.toml      packages/docintel-core/pyproject.toml
COPY packages/docintel-api/pyproject.toml       packages/docintel-api/pyproject.toml
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
# Also sync docintel-index — the Phase 13 entrypoint (docker/entrypoint-api.sh,
# UI-06 / D-18) invokes `docintel-index build` at container startup to
# bootstrap the stub/NumPy index on a fresh clone (data/indices/ is gitignored).
# Phase 13 gap closure 13-08: ALSO sync docintel-generate + docintel-retrieve.
# `docintel-index build` instantiates the stub LLM adapter via
# `docintel_core.adapters.factory.make_adapters`, which at module-load time
# imports `docintel_generate.parse._CHUNK_RE` (stub LLM emits chunk-id-
# delimited synthetic answers — see Plan 06-05). docintel-retrieve is the
# other half of the Generator the api uses for POST /query. Without these
# the entrypoint exits 1 before uvicorn starts, masquerading as a CR-01-
# style "demo doesn't work on fresh clone" failure.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
        --package docintel-api \
        --package docintel-index \
        --package docintel-generate \
        --package docintel-retrieve

# Pre-warm bge-reranker-base into HF_HOME=/opt/hf-cache so /health on a
# no-network reviewer machine works on the first call.
# (Phase 5 will actually invoke the reranker; Phase 1 just bakes the layer.)
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"

# Phase 13 UI-06 entrypoint: builds the stub index + seeds traces, then exec
# uvicorn (PID 1 for correct SIGTERM handling — see docker/entrypoint-api.sh).
# Replaces the pre-Phase-13 CMD ["uvicorn", ...]; the entrypoint exec's
# uvicorn directly so there is no separate CMD.
COPY docker/entrypoint-api.sh /entrypoint-api.sh
RUN chmod +x /entrypoint-api.sh

# Phase 13 gap closure 13-08 (CR-01): the entrypoint runs `docintel-index build`,
# which reads `/app/data/corpus/MANIFEST.json`. `data/indices/` is gitignored
# so a fresh clone has no index; without the corpus baked into the image the
# entrypoint raises FileNotFoundError and `set -eu` aborts before uvicorn
# starts. Selective COPY (NOT wholesale `COPY data/`) keeps the image
# deterministic — it pulls only tracked subdirs, never the gitignored runtime
# trees `data/indices/`, `data/traces/`, `data/eval/cache/` that would leak
# host-developer state. Placed AFTER the uv sync layers so changes under
# `data/eval/reports/<timestamp>/` (which the user pastes real-mode numbers
# into per `docs/REAL-RUN-CHECKLIST.md`) only bust this cheap data layer,
# never the expensive base-layer / uv-sync layers.
COPY data/corpus/ /app/data/corpus/
COPY data/eval/traces-seed.jsonl /app/data/eval/traces-seed.jsonl

EXPOSE 8000

# start-period raised 10s -> 30s to cover first-run `docintel-index build`
# inside the entrypoint (Assumption A4): the stub/NumPy build is fast but
# Python import + uv environment cold-start can take a few seconds on first
# container boot. Subsequent starts hit the idempotent MANIFEST.json skip
# path (~ms). retries=3 × interval=10s remains a hard 30s ceiling after
# start-period for catching genuinely broken containers.
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/entrypoint-api.sh"]
