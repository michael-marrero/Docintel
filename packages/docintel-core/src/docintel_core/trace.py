"""Entry-point-agnostic trace collector + JSONL sink + read helper (OBS-01/OBS-02).

Phase 12 data layer. Lives in ``docintel-core`` because BOTH consumers import it:
the API pure-ASGI middleware (Plan 12-04, D-01) and the eval runner's per-question
loop (Plan 12-03, D-02). ``docintel-eval`` cannot depend on ``docintel-api``, but
both depend on core — so the single shared collector lives here (RESEARCH
"Alternatives Considered" verdict).

Design (RESEARCH § Pattern 1, D-04):

* ``TraceSpanCollector`` is a context manager. On enter it binds ``trace_id`` into
  ``structlog.contextvars`` so every downstream log line carries it via the
  already-wired ``merge_contextvars`` processor (``log.py`` — NOT modified here).
  Stages are timed by the ENCLOSED ``with collector.span(name)`` block, never by
  reading a contextvar span-list after ``call_next`` (the Starlette
  ``BaseHTTPMiddleware`` upward-propagation failure, RESEARCH Pitfall 1) and never
  by parsing the existing ``retriever_search_completed`` / ``generator_completed``
  emitters (D-04 forbids coupling to them — top-level token/cost numbers are
  *copied* via ``add_fields`` from the generator's return value, never re-measured).
* On exit it writes exactly ONE consolidated ``trace_completed`` JSON line to the
  JSONL sink via an explicit writer (NOT a structlog processor, RESEARCH Pitfall 3),
  then clears the bound contextvars in a ``finally`` so a stale ``trace_id`` can
  never mislabel the next trace's logs (D-01 leak guard, RESEARCH Pitfall 2).

Security (this plan owns three controls — RESEARCH § Security Domain):

* T-12-01 (Tampering): the sink filename is collector-controlled (a per-process
  run id), NEVER request-derived; the resolved write path is asserted to be
  within ``trace_dir`` (V12 path-confinement). ``load_traces`` is likewise
  confined to ``trace_dir``.
* T-12-02 (Information Disclosure): records are METADATA-ONLY (timings, tokens,
  cost, model, ids, refused) — callers pass the cost *number*, not the completion
  object; no raw query/answer text, no ``SecretStr``, no API keys (V7).
* T-12-03 (Info Disclosure / Repudiation): ``clear_contextvars()`` in the ``finally``.

FND-11: ``trace.py`` MUST NOT read the environment. ``trace_dir`` arrives as a
constructor argument (from ``Settings.trace_dir``); ``config.py`` is the only env
reader (D-03).
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import structlog
from pydantic import BaseModel, ConfigDict

log = structlog.stdlib.get_logger(__name__)


class StageSpan(BaseModel):
    """One timed stage in a trace timeline (e.g. ``retrieval``, ``generation``).

    Frozen + ``extra="forbid"`` — mirrors every other DTO in ``types.py``
    (``RetrievedChunk``) and ``metrics.py`` (``QueryTimingRecord``). The optional
    ``fields`` payload carries sub-stage detail *copied* from a stage's existing
    telemetry return values (e.g. ``{"bm25_ms": ..., "rerank_ms": ...}`` or
    ``{"prompt_tokens": ...}``) — never re-measured, never scraped from a log line.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    # Wall-clock duration of the timed block, rounded to 2 decimals to match the
    # existing emitters (retriever.py:310 / generator.py:312).
    duration_ms: float
    fields: dict[str, Any] = {}

    def to_record(self) -> dict[str, Any]:
        """Flatten to the on-disk span shape: ``{name, duration_ms, **fields}``."""
        return {"name": self.name, "duration_ms": self.duration_ms, **self.fields}


class TraceSpanCollector:
    """Entry-point-agnostic trace collector (context manager).

    Open it once per logical request/question::

        with TraceSpanCollector(cfg.trace_dir, source="eval") as tc:
            with tc.span("retrieval"):
                ...
            with tc.span("generation"):
                ...
            tc.add_fields(cost_usd=..., model=...)

    On enter it binds ``trace_id`` into ``structlog.contextvars`` (so every
    downstream log line carries it via ``merge_contextvars``). On exit it appends
    one consolidated ``trace_completed`` JSON line to ``<trace_dir>/<sink_filename>``
    and clears the bound contextvars (D-01 leak guard).

    ``trace_dir`` arrives as a constructor arg (from ``Settings.trace_dir``) — this
    module never reads env (FND-11). ``source`` is ``"api"`` or ``"eval"``
    (provenance for the Phase 13 UI). ``sink_filename`` defaults to a per-process
    run file (never request-derived — Security V12 path-confinement).
    """

    def __init__(
        self,
        trace_dir: str,
        *,
        trace_id: str | None = None,
        source: str,
        sink_filename: str | None = None,
    ) -> None:
        self._trace_dir = Path(trace_dir)
        self._trace_id = trace_id if trace_id is not None else str(uuid.uuid4())
        self._source = source
        # Collector-controlled, per-process sink filename (NEVER request-derived,
        # Security T-12-01). One file per process run; many traces append to it.
        self._sink_filename = sink_filename if sink_filename is not None else _default_sink_filename()
        self._spans: list[StageSpan] = []
        self._fields: dict[str, Any] = {}
        self._start_perf: float = 0.0

    @property
    def trace_id(self) -> str:
        """The trace id bound for this request/question (UUID4 if not supplied)."""
        return self._trace_id

    def __enter__(self) -> TraceSpanCollector:
        # OBS-01: bind trace_id so merge_contextvars surfaces it on every
        # downstream log line (the untouched retriever/generator emitters included).
        structlog.contextvars.bind_contextvars(trace_id=self._trace_id)
        self._start_perf = time.perf_counter()
        return self

    @contextmanager
    def span(self, name: str, **fields: Any) -> Iterator[None]:
        """Time a stage and append an ordered :class:`StageSpan` on exit.

        Uses ``time.perf_counter`` — the same clock the retriever/runner use — so
        span ms are comparable to the existing emitters; rounded to 2 decimals to
        match their formatting. Nestable/sequential. The span is appended even if
        the body raises, so a failed stage still shows up on the timeline.
        """
        t0 = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            self._spans.append(StageSpan(name=name, duration_ms=duration_ms, fields=dict(fields)))

    def add_fields(self, **fields: Any) -> None:
        """Stash top-level fields for the final record (tokens, cost, model,
        refused, question_id) — copied from the generator's *return value* numbers
        (e.g. ``result.completion.cost_usd``), never re-measured and never the
        completion object itself (Security T-12-02: metadata-only)."""
        self._fields.update(fields)

    def _assemble_record(self) -> dict[str, Any]:
        """Build the consolidated ``trace_completed`` record (metadata only)."""
        return {
            "trace_id": self._trace_id,
            "source": self._source,
            "total_ms": round((time.perf_counter() - self._start_perf) * 1000, 2),
            "spans": [s.to_record() for s in self._spans],
            **self._fields,
        }

    def _sink_path(self) -> Path:
        """Resolve the sink path and confine it within ``trace_dir`` (V12).

        The filename is collector-controlled, but resolve-and-assert anyway as
        defense-in-depth against a future caller passing a traversal-laden name.
        """
        base = self._trace_dir.resolve()
        target = (self._trace_dir / self._sink_filename).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"sink path {target} escapes trace_dir {base}")
        return target

    def __exit__(self, *exc: object) -> None:
        try:
            record = self._assemble_record()
            sink = self._sink_path()
            sink.parent.mkdir(parents=True, exist_ok=True)
            with sink.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            # Stdout parity: the consolidated record also flows through structlog
            # (D-04 — copies the numbers, never re-measures). Still carries
            # trace_id via merge_contextvars until the clear below.
            log.info("trace_completed", **record)
        finally:
            # D-01 leak guard (RESEARCH Pitfall 2): clear in finally so a stale
            # trace_id can never leak into the next request even if the body raised.
            structlog.contextvars.clear_contextvars()


def _default_sink_filename() -> str:
    """Per-process run sink name. Collector-controlled (NOT request-derived)."""
    return f"traces-{uuid.uuid4().hex}.jsonl"


def load_traces(trace_dir: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read consolidated ``trace_completed`` records from ``trace_dir``/*.jsonl.

    Phase 13's Traces tab + ``GET /trace/{id}`` consume this; Phase 12 only
    produces it. Records are returned **newest-last** (files sorted by name, lines
    in append order). Tolerates a missing directory (returns ``[]``) and skips
    malformed lines defensively — a half-written final line must never crash the
    reader. Path-confined to ``trace_dir`` (only ``*.jsonl`` directly under it are
    read; Security V12). ``limit`` caps the number of returned records (the most
    recent ``limit``) when set.
    """
    base = Path(trace_dir)
    if not base.is_dir():
        return []

    records: list[dict[str, Any]] = []
    for sink in sorted(base.glob("*.jsonl")):
        if not sink.is_file():
            continue
        for line in sink.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                # Defensive: skip a malformed (e.g. half-written) line, never raise.
                continue
            if isinstance(parsed, dict):
                records.append(parsed)

    if limit is not None:
        return records[-limit:]
    return records
