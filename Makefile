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
        serve demo down fetch-corpus build-indices eval

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
# Pending targets — print the future-phase pointer and exit 1.
# CONTEXT.md D-22 explicitly says these are NOT no-ops.
# ---------------------------------------------------------------------------

eval: ## Lands in Phases 9–10 — eval CLI (EV2-* / EV3-*).
	@echo "make eval: not yet implemented in Phase 1." >&2
	@echo "Lands in Phases 9–10 — see .planning/REQUIREMENTS.md (EV2-* / EV3-*)." >&2
	@exit 1
