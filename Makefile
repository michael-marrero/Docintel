# docintel — Makefile
#
# Targets are split into two groups:
#   * Working: test, build, serve, demo, help, lint, format, lock-check,
#     fetch-corpus (Phase 3), build-indices (Phase 4)
#   * Stubbed (exit 1) until the named phase: eval (Phases 9–10)
#
# CONTEXT.md D-22 / D-23: stubs print what they will do, name the future phase,
# and exit 1. They are NOT no-ops.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Resolve git SHA for Docker builds; falls back to "unknown" outside a checkout.
GIT_SHA := $(shell git rev-parse HEAD 2>/dev/null || echo unknown)

.PHONY: help test lint format lock-check build build-api build-ui \
        serve demo down fetch-corpus build-indices ablate-chunk-sweep eval

help: ## Show all targets with their current status
	@echo "docintel — Makefile targets"
	@echo ""
	@echo "  Working:"
	@echo "    test           run uv run pytest"
	@echo "    lint           run ruff + black --check + mypy --strict"
	@echo "    format         run ruff format and black"
	@echo "    lock-check     uv lock --check (lockfile in sync with pyprojects)"
	@echo "    fetch-corpus   fetch + normalize + chunk SEC 10-K corpus (Phase 3)"
	@echo "    build-indices  build dense + BM25 indices from the corpus (Phase 4)"
	@echo "    ablate-chunk-sweep  Phase 11 ABL-01 chunk-size sweep {300,450,600} — REAL-mode only; alternate indices are gitignored"
	@echo "    build          docker build both api and ui targets"
	@echo "    build-api      docker build --target api"
	@echo "    build-ui       docker build --target ui"
	@echo "    serve          docker compose up (foreground)"
	@echo "    demo           alias of serve (will diverge in Phase 13)"
	@echo "    down           docker compose down"
	@echo "    help           this message"
	@echo ""
	@echo "  Pending (exit 1 until the named phase ships):"
	@echo "    eval           lands in Phases 9–10 (EV2-* / EV3-* — eval CLI)"

test: ## Run the test suite
	uv run pytest

lint: ## Run ruff + black --check + mypy --strict on packages/*/src
	uv run ruff check packages/
	uv run black --check packages/
	uv run mypy --strict packages/*/src

format: ## Auto-format with ruff and black
	uv run ruff check --fix packages/
	uv run ruff format packages/
	uv run black packages/

lock-check: ## Fail if uv.lock is out of sync with pyproject.toml(s)
	uv lock --check

build: build-api build-ui ## Build both Docker targets

build-api: ## Build the api Docker image
	docker build --target api -t docintel-api:local --build-arg GIT_SHA=$(GIT_SHA) -f docker/Dockerfile .

build-ui: ## Build the ui Docker image
	docker build --target ui -t docintel-ui:local --build-arg GIT_SHA=$(GIT_SHA) -f docker/Dockerfile .

serve: ## docker compose up (both api and ui)
	GIT_SHA=$(GIT_SHA) docker compose up

demo: serve ## Alias of `serve` in Phase 1; Phase 13 will pre-load demo data first

down: ## docker compose down (and remove the docintel network)
	docker compose down

# ---------------------------------------------------------------------------
# Phase 3 (ING-01..04): fetch + normalize + chunk + manifest the SEC 10-K corpus.
# Body invokes the docintel-ingest CLI's `all` subcommand which orchestrates
# the full pipeline. Re-runs are byte-identical (ING-04 idempotency contract
# enforced by tests/test_chunk_idempotency.py on every CI push).
# ---------------------------------------------------------------------------

fetch-corpus: ## Phase 3: fetch + normalize + chunk + manifest SEC 10-K corpus.
	uv run docintel-ingest all

# ---------------------------------------------------------------------------
# Phase 4 (IDX-01..04): build dense + BM25 indices from the committed corpus.
# Body invokes the docintel-index CLI's `all` subcommand (build → verify).
# Re-runs are idempotent — skip-if-corpus-MANIFEST-unchanged (D-12). Stub-mode
# runtime < 10s for 6,053 chunks; real-mode (Qdrant) < 3 min on CPU.
# ---------------------------------------------------------------------------

build-indices: ## Phase 4: build dense + BM25 indices from the committed corpus.
	uv run docintel-index all

# ---------------------------------------------------------------------------
# Phase 11 (ABL-01 / D-04 / D-05): chunk-size sweep build target. REAL-mode ONLY
# (invoked solely by the workflow_dispatch real job, Plan 05 — never on a PR;
# re-chunk -> re-embed -> re-index x3 sizes is the real-pipeline cost offline-
# first stub-CI avoids). For each size S in {300,450,600} it re-chunks the
# committed normalized corpus at S and builds a size-specific index, by
# OVERRIDING the EXISTING env-backed Settings fields DOCINTEL_DATA_DIR /
# DOCINTEL_INDEX_DIR at invocation — NO new env var (FND-11). A1: only the
# greedy split point is swept; overlap (50) + hard cap (500) stay fixed.
#
# Layout (per size S, all under data/indices/ so gitignored by the umbrella
# rule at .gitignore:24 — A3): a per-size data root data/indices/chunk-S/data/
# whose corpus/ reuses the production raw/normalized/snapshot (symlinked, never
# rewritten — T-11-10) and holds the size-S chunks + a size-S corpus MANIFEST.
# build_indices reads corpus_root=cfg.data_dir/corpus (chunks + MANIFEST.json
# for the corpus identity hash) and writes index_root=cfg.index_dir, so pointing
# DOCINTEL_DATA_DIR at the per-size data root and DOCINTEL_INDEX_DIR at
# data/indices/chunk-S/index makes the size-S chunks discoverable and the index
# land in the gitignored size root. The size-S corpus MANIFEST records
# chunker.target_tokens=S (write_manifest threads it), so each size gets a
# distinct corpus_manifest_sha256 -> distinct index identity for free (D-05).
# The 450 arm reuses the production corpus/index as the baseline (no rebuild).
# ---------------------------------------------------------------------------

ablate-chunk-sweep: ## Phase 11 ABL-01 chunk-size sweep {300,450,600} — REAL-mode only; alternate indices are gitignored.
	@for S in 300 450 600; do \
	  if [ "$$S" = "450" ]; then \
	    echo "ablate-chunk-sweep: size 450 reuses the production corpus/index (baseline) — no rebuild"; \
	    continue; \
	  fi; \
	  ROOT="data/indices/chunk-$$S"; \
	  DATA="$$ROOT/data"; \
	  CORPUS="$$DATA/corpus"; \
	  echo "ablate-chunk-sweep: building size-$$S index under $$ROOT (gitignored)"; \
	  rm -rf "$$ROOT"; \
	  mkdir -p "$$CORPUS/chunks" "$$ROOT/index"; \
	  ln -s "$(CURDIR)/data/corpus/raw" "$$CORPUS/raw"; \
	  ln -s "$(CURDIR)/data/corpus/normalized" "$$CORPUS/normalized"; \
	  ln -s "$(CURDIR)/data/corpus/companies.snapshot.csv" "$$CORPUS/companies.snapshot.csv"; \
	  uv run docintel-ingest chunk \
	    --normalized-root "$$CORPUS/normalized" \
	    --out-root "$$CORPUS/chunks" \
	    --target-tokens "$$S"; \
	  DOCINTEL_DATA_DIR="$$DATA" \
	    uv run python -c "from docintel_core.config import Settings; from docintel_ingest.manifest import write_manifest; write_manifest(Settings(), target_tokens=$$S)"; \
	  DOCINTEL_DATA_DIR="$$DATA" DOCINTEL_INDEX_DIR="$$ROOT/index" \
	    uv run docintel-index all; \
	done
	@echo "ablate-chunk-sweep: complete — size-300/600 indices built under data/indices/chunk-{300,600}/index (gitignored); 450 = production baseline"

# ---------------------------------------------------------------------------
# Pending targets — print the future-phase pointer and exit 1.
# CONTEXT.md D-22 explicitly says these are NOT no-ops.
# ---------------------------------------------------------------------------

eval: ## Lands in Phases 9–10 — eval CLI (EV2-* / EV3-*).
	@echo "make eval: not yet implemented in Phase 1." >&2
	@echo "Lands in Phases 9–10 — see .planning/REQUIREMENTS.md (EV2-* / EV3-*)." >&2
	@exit 1
