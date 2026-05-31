#!/bin/sh
# docintel API container entrypoint (Phase 13 D-18, UI-06).
#
# Bootstraps the API container so a fresh `git clone && docker-compose up`
# produces a working demo with zero API keys:
#
#   1. Build the stub/NumPy index (DOCINTEL_LLM_PROVIDER=stub) if MANIFEST.json
#      is absent — data/indices/ is gitignored, so a fresh clone has no index
#      and POST /query would otherwise return 500 on the first request.
#      The build is idempotent (IDX-03): subsequent starts see MANIFEST.json
#      and skip the build.
#
#   2. Seed data/traces/ from the committed sample at data/eval/traces-seed.jsonl
#      (RESEARCH Option B — the seed lives OUTSIDE data/traces/ so the
#      .gitignore split stays simple) if trace_dir is empty, so the Streamlit
#      Traces tab renders something before the first query.
#
#   3. `exec uvicorn` so uvicorn becomes PID 1 — Docker SIGTERM goes directly
#      to uvicorn (instead of to the shell parent that ignores it), so
#      `docker-compose down` is fast and graceful.
#
# Safety:
#   * `set -e` (RESEARCH Pitfall 6): a failed `docintel-index build` stops the
#     container BEFORE uvicorn starts, surfacing as unhealthy with a clear
#     error rather than serving 500s on every /query call.
#   * No interactive progress bars — docintel-index uses structlog JSON
#     logging, which works fine in a non-TTY container context.
#
# FND-11 spirit: read DOCINTEL_DATA_DIR (the env the compose service sets);
# do NOT hardcode /app/data. Defaults to `data` so the script also works
# when invoked from a host shell at the repo root for debugging.

set -eu

DATA_DIR="${DOCINTEL_DATA_DIR:-data}"
INDEX_MANIFEST="${DATA_DIR}/indices/MANIFEST.json"
TRACE_DIR="${DATA_DIR}/traces"
TRACE_SEED="${DATA_DIR}/eval/traces-seed.jsonl"

echo "[entrypoint] DOCINTEL_DATA_DIR=${DATA_DIR}"

# Step 1: build stub index if absent (idempotent — IDX-03).
if [ ! -f "${INDEX_MANIFEST}" ]; then
    echo "[entrypoint] No MANIFEST.json at ${INDEX_MANIFEST} — running docintel-index build (stub/NumPy)..."
    docintel-index build
    echo "[entrypoint] Stub index built."
else
    echo "[entrypoint] MANIFEST.json present at ${INDEX_MANIFEST} — skipping index build."
fi

# Step 2: seed traces tab so it renders before the first query (D-18).
if [ ! -d "${TRACE_DIR}" ] || [ -z "$(ls -A "${TRACE_DIR}" 2>/dev/null)" ]; then
    if [ -f "${TRACE_SEED}" ]; then
        echo "[entrypoint] Seeding ${TRACE_DIR} from ${TRACE_SEED}..."
        mkdir -p "${TRACE_DIR}"
        cp "${TRACE_SEED}" "${TRACE_DIR}/seed.jsonl"
    else
        echo "[entrypoint] No trace seed at ${TRACE_SEED} — Traces tab will be empty until first query."
    fi
else
    echo "[entrypoint] ${TRACE_DIR} already populated — skipping trace seed."
fi

# Step 3: hand off to uvicorn as PID 1 (exec replaces the shell process).
echo "[entrypoint] Starting uvicorn..."
exec uvicorn docintel_api.main:app --host 0.0.0.0 --port 8000
