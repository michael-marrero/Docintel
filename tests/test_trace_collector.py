"""Plan 12-01 Wave 0 xfail-strict scaffold for the OBS-01/OBS-02 trace collector.

Covers 12-VALIDATION.md rows V-04..V-07 — the ``TraceSpanCollector`` +
``load_traces()`` contract that Plan 12-02 ships in
``packages/docintel-core/src/docintel_core/trace.py``:

* test_contextvars_cleared_between_traces (V-04) — open collector A as a
  ``with``, exit; A's trace_id must be gone from ``structlog.contextvars``;
  open collector B; only B's id is present. The leak-guard test
  (RESEARCH Pitfall 2 / Security Information-Disclosure — ``clear_contextvars``
  in ``__exit__``'s ``finally``).
* test_writes_one_record_per_trace (V-05) — point the collector at
  ``tmp_path`` as ``trace_dir``; on ``with`` exit exactly one line is appended
  to the JSONL sink and ``json.loads`` succeeds.
* test_record_schema_well_formed (V-06) — the loaded record carries
  ``trace_id``, ``source``, an ordered ``spans`` list (each element has
  ``name`` + ``duration_ms``), and the top-level token/cost fields attached
  via ``add_fields``. Asserts **presence + types + span ordering**, NOT exact
  ms values (RESEARCH A4 — trace records carry real wall-clock ms and are
  gitignored). Mirrors the named-field-presence subset assertion from
  ``tests/test_generator_telemetry.py``.
* test_load_traces_roundtrip (V-07) — write N traces, ``load_traces(tmp_path)``
  returns N dicts matching what was written; a missing dir returns ``[]``; a
  deliberately malformed final line is tolerated (skipped, never raises).

Wave-0 semantics (project xfail-first convention, Phases 6-11): every test
is ``@pytest.mark.xfail(strict=True, ...)``. ``docintel_core.trace`` does not
exist until Plan 12-02 — the module-top import raises ImportError, which is
the expected strict-xfail trigger at collection... so the import is deferred
into each test body (so pytest collection never crashes before Wave 1 ships
the implementation). Plan 12-05's xfail-removal sweep flips these to green.

Analogs:
* ``tests/test_generator_telemetry.py:1-52`` + ``tests/test_retriever_search.py:121-163``
  — the ``capture_logs`` + named-field-presence assertion convention.
* ``tests/test_metrics.py`` — the Phase 9 xfail-strict scaffold (deferred
  import is the ImportError xfail trigger).
* 12-RESEARCH.md §"Pattern 1" lines 197-273 (TraceSpanCollector signatures)
  + §"load_traces()" lines 582-594.
* 12-PATTERNS.md §"structlog capture_logs test pattern".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog


@pytest.mark.xfail(strict=True, reason="Phase 12 12-02 implements docintel_core.trace.TraceSpanCollector")
def test_contextvars_cleared_between_traces(tmp_path: Path) -> None:
    """V-04 — contextvars cleared between traces; no leakage (RESEARCH Pitfall 2).

    Open collector A as a ``with`` and exit it; its ``trace_id`` must no longer
    be present in ``structlog.contextvars``. Then open collector B and assert
    only B's ``trace_id`` is bound. This is the OBS-01 leak guard — the
    collector's ``__exit__`` must ``clear_contextvars()`` in a ``finally`` so a
    trace_id never leaks into the next request/question (Security
    Information-Disclosure).
    """
    from docintel_core.trace import TraceSpanCollector  # ImportError until Plan 12-02

    structlog.contextvars.clear_contextvars()

    with TraceSpanCollector(str(tmp_path), source="eval") as tc_a:
        id_a = tc_a.trace_id
        assert structlog.contextvars.get_contextvars().get("trace_id") == id_a
    # A exited: its id must be gone (leak guard).
    assert structlog.contextvars.get_contextvars().get("trace_id") != id_a

    with TraceSpanCollector(str(tmp_path), source="eval") as tc_b:
        id_b = tc_b.trace_id
        bound = structlog.contextvars.get_contextvars()
        assert bound.get("trace_id") == id_b
        # Only B is present — A did not leak across the boundary.
        assert id_b != id_a


@pytest.mark.xfail(strict=True, reason="Phase 12 12-02 implements docintel_core.trace.TraceSpanCollector")
def test_writes_one_record_per_trace(tmp_path: Path) -> None:
    """V-05 — exactly one consolidated trace_completed JSON line per trace.

    Point the collector at ``tmp_path`` as ``trace_dir``. On ``with`` exit the
    sink must contain exactly one appended line, and ``json.loads`` must parse
    it (one consolidated ``trace_completed`` record per request — D-04).
    """
    from docintel_core.trace import TraceSpanCollector  # ImportError until Plan 12-02

    with TraceSpanCollector(str(tmp_path), source="eval") as tc:
        with tc.span("retrieval"):
            pass
        with tc.span("generation"):
            pass
        tc.add_fields(cost_usd=0.0, model="stub-refusal")

    sink_files = list(tmp_path.glob("*.jsonl"))
    assert len(sink_files) == 1, f"expected exactly one sink file; got {sink_files!r}"
    lines = [ln for ln in sink_files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one trace_completed line; got {len(lines)}"
    record = json.loads(lines[0])
    assert record["trace_id"] == tc.trace_id


@pytest.mark.xfail(strict=True, reason="Phase 12 12-02 implements docintel_core.trace.TraceSpanCollector")
def test_record_schema_well_formed(tmp_path: Path) -> None:
    """V-06 — record is well-formed: trace_id, source, ordered spans[], token/cost.

    Assert **presence + types + span ordering**, NOT exact ms values
    (RESEARCH A4 — trace records carry real wall-clock ms and are gitignored).
    Mirrors the named-field-presence subset assertion from
    ``tests/test_generator_telemetry.py``: the named fields must be a subset of
    the record's keys (so a future plan ADDING a sibling field does not go red
    here — only a REMOVED named field does).
    """
    from docintel_core.trace import TraceSpanCollector, load_traces  # ImportError until Plan 12-02

    with TraceSpanCollector(str(tmp_path), source="eval") as tc:
        with tc.span("retrieval"):
            pass
        with tc.span("generation"):
            pass
        tc.add_fields(
            question_id="GT-comparative-001",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.0,
            model="stub-refusal",
        )

    records = load_traces(str(tmp_path))
    assert len(records) == 1
    rec = records[0]

    # Top-level presence (subset, not cardinality).
    required_top = {"trace_id", "source", "spans", "cost_usd", "model"}
    missing = required_top - set(rec.keys())
    assert not missing, f"V-06 record missing top-level fields: {sorted(missing)!r}"

    # Types.
    assert isinstance(rec["trace_id"], str) and rec["trace_id"]
    assert rec["source"] == "eval"
    assert isinstance(rec["spans"], list) and len(rec["spans"]) == 2

    # Each span has name + duration_ms; duration_ms is a non-negative number
    # (presence + type only — NOT an exact ms value, RESEARCH A4).
    for span in rec["spans"]:
        assert {"name", "duration_ms"} <= set(span.keys()), f"span missing fields: {span!r}"
        assert isinstance(span["duration_ms"], (int, float))
        assert span["duration_ms"] >= 0.0

    # Span ordering is preserved (retrieval recorded before generation).
    assert [s["name"] for s in rec["spans"]] == ["retrieval", "generation"]


@pytest.mark.xfail(strict=True, reason="Phase 12 12-02 implements docintel_core.trace.load_traces")
def test_load_traces_roundtrip(tmp_path: Path) -> None:
    """V-07 — load_traces round-trips the writer; missing dir -> []; malformed line tolerated.

    Write N traces via the collector, then ``load_traces(tmp_path)`` must return
    N dicts matching what was written. ``load_traces`` on a missing directory
    returns ``[]``. A deliberately-appended malformed final line (a half-written
    record) must be tolerated — skipped, never raised (RESEARCH lines 585-592).
    """
    from docintel_core.trace import TraceSpanCollector, load_traces  # ImportError until Plan 12-02

    # Missing dir -> [].
    assert load_traces(str(tmp_path / "does_not_exist")) == []

    n = 3
    written_ids: list[str] = []
    for _ in range(n):
        with TraceSpanCollector(str(tmp_path), source="eval") as tc:
            with tc.span("retrieval"):
                pass
            written_ids.append(tc.trace_id)

    records = load_traces(str(tmp_path))
    assert len(records) == n
    assert {r["trace_id"] for r in records} == set(written_ids)

    # Append a deliberately malformed final line to the sink; the reader must
    # tolerate it (skip it) and still return the N well-formed records.
    sink = next(tmp_path.glob("*.jsonl"))
    with sink.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
    records_after = load_traces(str(tmp_path))
    assert len(records_after) == n, "malformed final line must be skipped, not crash the reader"
