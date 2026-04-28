# docintel — Makefile
#
# Targets are split into two groups:
#   * Working in Phase 1: test, build, serve, demo, help, lint, format, lock-check
#   * Stubbed (exit 1) until the named phase: fetch-corpus, ingest, eval
#
# CONTEXT.md D-22 / D-23: stubs print what they will do, name the future phase,
# and exit 1. They are NOT no-ops.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Resolve git SHA for Docker builds; falls back to "unknown" outside a checkout.
GIT_SHA := $(shell git rev-parse HEAD 2>/dev/null || echo unknown)

.PHONY: help test lint format lock-check build build-api build-ui \
        serve demo down fetch-corpus ingest eval

help: ## Show all targets with their current status
	@echo "docintel — Makefile targets"
	@echo ""
	@echo "  Working in Phase 1:"
	@echo "    test           run uv run pytest"
	@echo "    lint           run ruff + black --check + mypy --strict"
	@echo "    format         run ruff format and black"
	@echo "    lock-check     uv lock --check (lockfile in sync with pyprojects)"
	@echo "    build          docker build both api and ui targets"
	@echo "    build-api      docker build --target api"
	@echo "    build-ui       docker build --target ui"
	@echo "    serve          docker compose up (foreground)"
	@echo "    demo           alias of serve (will diverge in Phase 13)"
	@echo "    down           docker compose down"
	@echo "    help           this message"
	@echo ""
	@echo "  Pending (exit 1 until the named phase ships):"
	@echo "    fetch-corpus   lands in Phase 3 (ING-* — corpus fetcher)"
	@echo "    ingest         lands in Phase 4 (IDX-05 — full ingest pipeline)"
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
# Pending targets — print the future-phase pointer and exit 1.
# CONTEXT.md D-22 explicitly says these are NOT no-ops.
# ---------------------------------------------------------------------------

fetch-corpus: ## Lands in Phase 3 — corpus fetcher (ING-*).
	@echo "make fetch-corpus: not yet implemented in Phase 1." >&2
	@echo "Lands in Phase 3 — see .planning/REQUIREMENTS.md (ING-* requirements)." >&2
	@exit 1

ingest: ## Lands in Phase 4 — ingest → chunk → embed → index pipeline (IDX-05).
	@echo "make ingest: not yet implemented in Phase 1." >&2
	@echo "Lands in Phase 4 — see .planning/REQUIREMENTS.md (IDX-05)." >&2
	@exit 1

eval: ## Lands in Phases 9–10 — eval CLI (EV2-* / EV3-*).
	@echo "make eval: not yet implemented in Phase 1." >&2
	@echo "Lands in Phases 9–10 — see .planning/REQUIREMENTS.md (EV2-* / EV3-*)." >&2
	@exit 1
