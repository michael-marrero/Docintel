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
from pathlib import Path
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
# /coverage  (Story 1.5 — the browsable coverage view's data source; AD-15)
# ---------------------------------------------------------------------------


class CoverageCompany(BaseModel):
    """One row of the coverage view: declared scope + indexed counts."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sector: str
    forms: list[str]
    fiscal_years: list[int]
    filing_counts: dict[str, int]
    transcript_count: int
    latest_period: str | None
    in_corpus: bool


class CoverageCorpus(BaseModel):
    """The corpus-wide coverage summary (the `CORPUS · N FILERS · FY..-FY..` label)."""

    model_config = ConfigDict(extra="forbid")

    company_count: int
    forms: list[str]
    fy_min: int | None
    fy_max: int | None
    has_transcripts: bool
    snapshot_date: str


class CoverageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus: CoverageCorpus
    companies: list[CoverageCompany]


@app.get("/coverage", response_model=CoverageResponse, tags=["coverage"])
def coverage() -> CoverageResponse:
    """Browsable corpus coverage: declared scope + indexed counts (Story 1.5).

    Backed by the ingest-layer coverage facade + the corpus MANIFEST. Lazy import
    keeps ``import docintel_api.main`` cheap (mirrors ``_generator``).
    """
    from docintel_ingest.coverage import build_coverage_view

    return CoverageResponse.model_validate(build_coverage_view(_settings()))


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
# GET /brief/{ticker} — Story 2.2 streaming structured cited brief (SSE)
# ---------------------------------------------------------------------------


def _covered_company(ticker: str) -> dict[str, Any] | None:
    """Return the coverage row for ``ticker`` if it is an indexed filer, else None.

    Lazy import (mirrors ``/coverage``) keeps ``import docintel_api.main`` cheap.
    """
    from docintel_ingest.coverage import build_coverage_view

    want = ticker.upper()
    for company in build_coverage_view(_settings()).get("companies", []):
        if str(company.get("ticker", "")).upper() == want and company.get("in_corpus"):
            return company
    return None


def _sse(event: str, payload: dict[str, Any]) -> str:
    """Frame one Server-Sent Event: ``event:`` line + one ``data:`` JSON line."""
    import json

    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@app.get("/brief/{ticker}", tags=["brief"])
def brief(ticker: str) -> Any:
    """Stream a four-section cited brief for ``ticker`` as Server-Sent Events.

    Emits one ``section`` event per section as it is generated (section-by-section,
    UX-DR16), then a terminal ``done`` event. An uncovered ticker yields a single
    ``refused`` event (full refusal UX is Story 2.6) — it routes, never fabricates.
    Same-origin plain HTTP (AD-15); the browser consumes it via ``EventSource``.
    """
    from fastapi.responses import StreamingResponse

    company = _covered_company(ticker)

    def stream() -> Any:
        if company is None:
            yield _sse("refused", {"ticker": ticker.upper(), "reason": "not a covered filer"})
            return

        from docintel_generate.brief import generate_brief

        gen = _generator()
        claims = 0
        n_sections = 0
        for section in generate_brief(gen, company["ticker"], company["name"]):
            answer = section.answer
            claims += len(answer.citations)
            n_sections += 1
            yield _sse(
                "section",
                {
                    "index": section.index,
                    "key": section.key,
                    "title": section.title,
                    "answer": answer.model_dump(),
                    "scores": section.scores,  # {chunk_id: rerank score} — Story 2.3 panel
                },
            )
        yield _sse(
            "done",
            {
                "ticker": company["ticker"],
                "name": company["name"],
                "sections": n_sections,
                "claims_cited": claims,
            },
        )

    return StreamingResponse(stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /trust — Story 3.9 in-app trust/accuracy panel (UX-DR10, AD-15)
# ---------------------------------------------------------------------------


class TrustResponse(BaseModel):
    """The proof-report headline the trust/accuracy panel renders (Story 3.9).

    ``source`` is ``"baseline"`` when the committed baseline-locked report was
    read, or ``"placeholder"`` when no proof report exists yet — so Epic 2's
    panel renders without a hard runtime dependency on Epic 3 (AC-2). The panel
    consumes THIS endpoint over HTTP only (AD-15); the server reads the committed
    report file, the browser never touches the filesystem.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["baseline", "placeholder"]
    representative: bool
    faithfulness: dict[str, Any] | None
    citation_accuracy: dict[str, Any] | None
    manifest: dict[str, Any] | None


def _placeholder_trust() -> TrustResponse:
    """No committed proof report → an honest placeholder (AC-2)."""
    return TrustResponse(
        source="placeholder",
        representative=False,
        faithfulness=None,
        citation_accuracy=None,
        manifest=None,
    )


@app.get("/trust", response_model=TrustResponse, tags=["trust"])
def trust() -> TrustResponse:
    """Serve the baseline-locked eval report's headline for the trust panel.

    Reads ``data/eval/baseline.json`` → the locked ``report_dir`` → its
    ``results.json`` (a committed repo artifact), and returns faithfulness +
    citation-accuracy + the manifest. Any missing/malformed artifact degrades to
    a placeholder rather than 500 — the panel must always render (AC-2).
    """
    import json

    baseline_path = Path("data/eval/baseline.json")
    if not baseline_path.is_file():
        return _placeholder_trust()
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        report_dir = Path(str(baseline.get("report_dir", ""))).resolve()
        # Confine under data/eval/reports/ (defense-in-depth on a trusted file).
        reports_root = Path("data/eval/reports").resolve()
        if not (report_dir == reports_root or reports_root in report_dir.parents):
            return _placeholder_trust()
        results = json.loads((report_dir / "results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _placeholder_trust()

    manifest = results.get("manifest", {})
    faith = results.get("faithfulness", {})
    per_q = results.get("per_question", [])

    # Citation accuracy headline: mean per-question citation precision over
    # non-refused answers that actually cited (n_citations > 0). Computed here —
    # results.json carries it per-question, not as a top-level field.
    answered = [r for r in per_q if not r.get("refused") and int(r.get("n_citations", 0)) > 0]
    if answered:
        cit_mean = sum(float(r.get("citation_precision", 0.0)) for r in answered) / len(answered)
        citation_accuracy: dict[str, Any] | None = {
            "precision": cit_mean,
            "n_answered": len(answered),
        }
    else:
        citation_accuracy = None

    return TrustResponse(
        source="baseline",
        representative=bool(manifest.get("representative", False)),
        faithfulness={
            "pass_rate": faith.get("faithfulness_pass_rate"),
            "ci": faith.get("faithfulness_ci"),
            "n_answered": faith.get("n_answered"),
        },
        citation_accuracy=citation_accuracy,
        manifest={
            k: manifest.get(k)
            for k in (
                "embedder_name",
                "reranker_name",
                "generator_name",
                "judge_name",
                "prompt_version_hash",
                "git_sha",
                "provider",
                "n_questions",
                "dataset_hash",
                "run_timestamp_utc",
                "representative",
            )
        },
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

    Only records that recorded at least one span are surfaced — the showcase is
    the RAG query pipeline (``POST /query`` writes a ``pipeline`` span). Requests
    that did no traced work (``/health``, ``/coverage`` on page load, etc.) write
    empty-span records; filtering them here keeps the query traces from being
    buried (Story 2.1 review). Static assets are already skipped upstream by the
    middleware, so they never reach the sink.
    """
    records = reversed(load_traces(_settings().trace_dir, limit=limit))
    return [rec for rec in records if rec.get("spans")]


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
# Static frontend (Story 2.1) — serve the dark-terminal web-app from web/.
#
# Mounted LAST so the API routes above (/health, /coverage, /query, /traces,
# /trace/{id}) always win; StaticFiles(html=True) then serves web/index.html at
# "/" and the static assets (app.js, app.css, lib.js, tokens.css) by path, and
# 404s unknown paths. Same-origin, so the frontend's fetch("/coverage") needs no
# CORS. The page touches the API over HTTP only (AD-15) — never the filesystem.
# ---------------------------------------------------------------------------


def _web_dir() -> Path | None:
    """Locate the frontend directory, or None if it isn't present.

    Not configuration (D-18 is about env-driven Settings) — a static-asset path
    derived from the package layout. Prefers the in-repo location
    (``<repo>/web``, resolved from this file); falls back to ``<cwd>/web`` so a
    container that runs uvicorn from a WORKDIR holding ``web/`` also resolves.
    """
    candidates = [
        Path(__file__).resolve().parents[4] / "web",  # in-repo + TestClient
        Path.cwd() / "web",  # container WORKDIR fallback
    ]
    for cand in candidates:
        if (cand / "index.html").is_file():
            return cand
    return None


_WEB_DIR = _web_dir()
if _WEB_DIR is not None:
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
else:
    # Fail open (API still boots) but say so — a silent blank page is not
    # diagnosable. In a pip-installed deploy, ensure the container copies web/
    # into a location _web_dir() can find (repo layout or the uvicorn WORKDIR).
    import structlog

    structlog.get_logger("docintel_api").warning(
        "web_dir_not_found", detail="frontend not found; GET / will 404 (UI disabled)"
    )


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
