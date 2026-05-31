"""FastAPI application for docintel.

Phase 1 scope: introspective GET /health only.
Phase 13 (Plan 13-02) adds POST /query, GET /traces, GET /trace/{id} (API-01).
Phase 2 will extend /health with adapter introspection — do NOT add it here.

Per CONTEXT.md D-18, this module MUST NOT read environment variables directly.
All configuration flows through docintel_core.config.Settings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Literal

from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging
from docintel_core.trace import load_traces
from docintel_core.types import Answer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware import Middleware
from starlette.requests import Request

from docintel_api.middleware import TraceIdMiddleware

# ---------------------------------------------------------------------------
# Configuration / app construction
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _settings() -> Settings:
    """Memoized Settings — Settings() reads env exactly once per process."""
    return Settings()


def reset_settings_cache() -> None:
    """Public hook for tests; clears the lru_cache on _settings().

    Tests must NOT import the underscore-prefixed `_settings` directly. They
    call this function to force a re-read of the environment between cases.
    """
    _settings.cache_clear()


@lru_cache(maxsize=1)
def _generator() -> Any:
    """Singleton Generator — constructed once, warm on every request (CD-05).

    Mirrors ``_settings()``: ``@lru_cache(maxsize=1)`` so the first POST /query
    pays the index-load + adapter-init cost (~600ms for 6053 chunks in stub
    mode); subsequent requests reuse the warm instance. The factory itself has
    NO factory-level cache (CD-05 in 06-RESEARCH); this is the dependency-layer
    cache the factory's CD-05 docstring anticipates ("Phase 13 FastAPI
    ``lru_cache``s the constructed Generator at the dependency-injection
    layer").

    Lazy import (Pattern S5, FND-12): the ``from
    docintel_core.adapters.factory import make_generator`` lives inside the
    body so ``import docintel_api.main`` stays cheap and the test xfail-strict
    scaffolds collected without the full RAG stack imported at module load.
    """
    from docintel_core.adapters.factory import make_generator

    return make_generator(_settings())


def reset_generator_cache() -> None:
    """Public hook for tests; clears the lru_cache on _generator().

    Mirrors ``reset_settings_cache()``. Tests that swap the Settings (e.g.
    point ``DOCINTEL_INDEX_DIR`` at a tmp dir) must clear this cache too so
    the next request rebuilds ``make_generator`` against the new settings.

    Defensive: tests that monkeypatch ``_generator`` itself (e.g. the refusal
    test that injects a stub returning ``refused=True``) replace the lru_cache
    function with a plain callable that has no ``cache_clear``. The teardown
    in the ``client`` fixture runs BEFORE ``monkeypatch.undo()``, so guard
    against the missing attribute instead of crashing the teardown.
    """
    cache_clear = getattr(_generator, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


configure_logging()

app = FastAPI(
    title="docintel API",
    version=__version__,
    description=(
        "Production-shaped RAG over SEC 10-K filings. " "Phase 1: scaffold + /health only."
    ),
    # OBS-01 / D-01: pure-ASGI trace_id binding for every request. Reuses the
    # existing _settings() accessor so config.py stays the only env reader
    # (FND-11). NOT BaseHTTPMiddleware — see docintel_api.middleware docstring.
    middleware=[Middleware(TraceIdMiddleware, settings=_settings())],
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Locked /health JSON shape — see CONTEXT.md D-15.

    Phase 2 may extend this model (e.g. adapters block); existing fields MUST
    NOT change shape or rename.
    """

    status: Literal["ok"]
    service: Literal["docintel-api"]
    version: str
    provider: Literal["stub", "real"]
    git_sha: str
    timestamp: str  # ISO-8601 UTC


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    settings = _settings()
    return HealthResponse(
        status="ok",
        service="docintel-api",
        version=__version__,
        provider=settings.llm_provider,
        git_sha=settings.git_sha,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


# ---------------------------------------------------------------------------
# POST /query — UI-01 query path; D-01/D-02; deferred Phase 12 D-05
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Locked POST /query request body — see CONTEXT.md D-05 ("free-text only").

    ``extra="forbid"`` is the T-13-02 input-validation gate (Security V5): the
    only accepted field is ``question``. Any unknown body field (e.g. an
    attempted ``company`` filter, a debug flag, a sneaky ``trace_id`` in body)
    is rejected at the route boundary with 422 — never silently ignored.

    A bounded ``max_length=2000`` (~ ~500 tokens of plain English) caps the DoS
    surface; legitimate research-style questions easily fit. ``min_length=1``
    rejects an empty body.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class TraceBlock(BaseModel):
    """Per-request trace block — surfaces the in-flight collector's spans.

    Mirrors the on-disk ``trace_completed`` record shape (``docintel_core.trace``)
    so the UI Query tab can render a cost/latency meter without a second fetch
    and the Traces tab can deep-link by ``trace_id``. ``spans`` is the list
    captured so far in the handler (the collector's consolidated record is only
    finalized on middleware exit, AFTER this handler returns — so the response
    builds ``total_ms`` from the ``pipeline`` span's duration, not from the
    not-yet-written consolidated record). ``cost_usd`` is the per-query cost
    surfaced via ``TraceSpanCollector.add_fields``.
    """

    trace_id: str
    spans: list[dict[str, Any]]
    total_ms: float
    cost_usd: float


class QueryResponse(BaseModel):
    """Locked POST /query response — answer + trace block (D-02).

    ``answer`` carries the full ``Answer`` shape (``text``, ``citations``,
    ``confidence``, ``refused``, ``prompt_version_hash``) the UI renders;
    ``trace`` carries the per-request timing/cost block. Both are required.
    Response model is plain dict for ``answer`` (not ``Answer``) because
    ``Answer.model_dump()`` is what the UI consumes and re-validating through
    a nested response_model would double-validate without semantic gain.
    """

    answer: dict[str, Any]
    trace: TraceBlock


@app.post("/query", response_model=QueryResponse, tags=["query"])
def query(req: QueryRequest, request: Request) -> QueryResponse:
    """Execute the RAG pipeline for ``req.question`` (UI-01, D-01/D-02).

    Reuses the middleware's TraceSpanCollector via ``request.state.trace_collector``
    (RESEARCH Pitfall 3) — wraps the ``Generator.generate(...)`` call in one
    ``pipeline`` span on the SAME collector so the middleware's __exit__ writes
    exactly ONE ``trace_completed`` record per request (no double-collector).
    Per-stage sub-spans are out of scope for Phase 13 — one ``pipeline`` span
    is correct and honest (CONTEXT canonical_refs, RESEARCH Focus Area 4).

    Trace id is read from the collector itself (bound by the middleware from
    ``X-Trace-Id`` per D-01). ``cost_usd`` + ``model`` + ``refused`` are
    copied from the generator's return value via ``add_fields`` — never
    re-measured (T-12-02: metadata-only; Phase 12 D-04).
    """
    import time

    tc = request.state.trace_collector

    gen = _generator()
    t0 = time.perf_counter()
    with tc.span("pipeline"):
        gr = gen.generate(req.question)
    pipeline_ms = round((time.perf_counter() - t0) * 1000, 2)
    answer = Answer.from_generation_result(gr)

    cost_usd = gr.completion.cost_usd if gr.completion else 0.0
    model = gr.completion.model if gr.completion else "stub"
    tc.add_fields(cost_usd=cost_usd, model=model, refused=gr.refused)

    # The collector's consolidated record is finalized in middleware __exit__
    # (AFTER this handler returns), so we cannot re-read load_traces mid-request
    # to populate the response — that would miss the not-yet-written record.
    # Build the trace block from a parallel measurement of the pipeline span we
    # just recorded (same wall-clock window; matches what the collector wrote).
    pipeline_span: dict[str, Any] = {"name": "pipeline", "duration_ms": pipeline_ms}

    return QueryResponse(
        answer=answer.model_dump(),
        trace=TraceBlock(
            trace_id=tc.trace_id,
            spans=[pipeline_span],
            total_ms=pipeline_ms,
            cost_usd=cost_usd,
        ),
    )


# ---------------------------------------------------------------------------
# GET /traces + GET /trace/{id} — UI-01 traces tab; D-10
# ---------------------------------------------------------------------------


def _is_valid_uuid(raw: str) -> bool:
    """True iff ``raw`` parses as a UUID — mirrors ``middleware._validate_trace_id``
    semantics (Security V5 / T-13-03 path-traversal guard).

    The ``{trace_id}`` path parameter is untrusted. A non-UUID string must
    never reach a filesystem path; ``load_traces`` is already path-confined to
    ``trace_dir`` (Phase 12 V12) but defense-in-depth: reject at the route
    boundary so attacker input cannot drive a wasted full-scan of the sink.
    """
    import uuid as _uuid

    try:
        _uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


@app.get("/traces", tags=["traces"])
def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent ``trace_completed`` records, newest-FIRST (D-10).

    ``load_traces`` returns newest-LAST (file-sorted + append-order; RESEARCH
    Pitfall 8); the UI Traces tab wants newest-first for the recent-queries
    table, so we ``reversed`` it here at the boundary. ``limit`` caps the
    response at a sane portfolio-scale default (50); pagination not required
    (CONTEXT "Claude's Discretion").
    """
    return list(reversed(load_traces(_settings().trace_dir, limit=limit)))


@app.get("/trace/{trace_id}", tags=["traces"])
def get_trace(trace_id: str) -> dict[str, Any]:
    """Return the single ``trace_completed`` record matching ``trace_id`` (D-10).

    UUID-validate ``trace_id`` BEFORE any filesystem read (T-13-03). On
    invalid OR unknown id: 404 — never 500, never a path read with attacker
    input. ``load_traces`` is path-confined to ``trace_dir`` (Phase 12 V12);
    this route is additionally guarded by the UUID check so a non-UUID id is
    rejected at the route boundary, not the helper.
    """
    if not _is_valid_uuid(trace_id):
        raise HTTPException(status_code=404, detail="trace not found")
    for record in load_traces(_settings().trace_dir):
        if record.get("trace_id") == trace_id:
            return record
    raise HTTPException(status_code=404, detail="trace not found")


# ---------------------------------------------------------------------------
# Console-script entrypoint (referenced by packages/docintel-api/pyproject.toml)
# ---------------------------------------------------------------------------


def run() -> None:
    """Launch uvicorn against this app. Used by the `docintel-api` console script."""
    import uvicorn

    uvicorn.run(
        "docintel_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None,  # let structlog/stdlib handle formatting
    )


if __name__ == "__main__":
    run()
