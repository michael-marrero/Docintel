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
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

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
# Also sync docintel-index — the Phase 13 entrypoint (docker/entrypoint-api.sh,
# UI-06 / D-18) invokes `docintel-index build` at container startup to
# bootstrap the stub/NumPy index on a fresh clone (data/indices/ is gitignored).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package docintel-api --package docintel-index

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


# ============================================================================
# Stage: ui — Streamlit UI (slim, no ML weights)
# ============================================================================
FROM base AS ui

# Install ui package + its deps (Streamlit, httpx). NO sentence-transformers
# in the ui image — keeps it well under 1 GiB.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package docintel-ui

# Phase 13 gap closure 13-08 (CR-01): the Eval-Results tab's
# `_find_eval_report(settings.data_dir)` reads `/app/data/eval/reports/...`;
# without these baked in the tab renders "No eval report found" on a fresh
# clone. Selective COPY — NOT the 55M corpus that the ui doesn't need;
# this keeps the ui image lean. No `traces-seed.jsonl` either — the ui
# fetches traces from the api over HTTP, never reads the seed directly.
COPY data/eval/reports/stub-sample/    /app/data/eval/reports/stub-sample/
COPY data/eval/ablations/stub-sample/  /app/data/eval/ablations/stub-sample/
COPY data/eval/ground_truth/           /app/data/eval/ground_truth/

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", \
     "/app/packages/docintel-ui/src/docintel_ui/streamlit_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
