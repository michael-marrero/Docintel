"""Plan 12-01 Wave 0 xfail-strict scaffold for OBS-02 / A3 eval-writes-traces.

Covers 12-VALIDATION.md row V-08 (A3, the recommended discretion accepted by
this phase's scope-fence): an eval run also writes consolidated
``trace_completed`` records to ``Settings.trace_dir``, giving the Phase 13
Traces tab real stub-mode demo data before ``POST /query`` exists (D-02).

* test_eval_run_writes_traces — run ``run_eval(cfg)`` against a ``tmp_path``
  ``trace_dir`` in stub mode (``DOCINTEL_LLM_PROVIDER=stub``). After the run,
  ``data/traces/`` (here ``tmp_path``) holds one consolidated trace record per
  ground-truth question, and ``json.loads`` parses each line. Asserts
  **count + shape/presence, NOT exact ms** (RESEARCH A4 — trace records carry
  real wall-clock ms and are gitignored).

Wave-0 semantics (project xfail-first convention, Phases 6-11): the test is
``@pytest.mark.xfail(strict=True, ...)``. At Wave 0 (a) ``Settings`` has no
``trace_dir`` field (lands in Plan 12-02) and (b) the eval runner does not yet
wrap each question in a ``TraceSpanCollector`` (lands in the eval-wiring plan),
so constructing ``Settings(trace_dir=...)`` / finding trace files fails — the
expected strict-xfail trigger. Imports are deferred into the test body so
collection never crashes. Plan 12-05's xfail-removal sweep flips this green.

Determinism note (RESEARCH A4): the runner zeroes ``total_ms`` in stub mode for
byte-identical report reruns, but ``data/traces/`` is gitignored and never
committed, so the collector may carry real wall-clock span ms. This test
asserts shape/presence, never exact ms.

Analogs:
* the existing ``tests/test_eval_*`` suite + the ``run_eval`` invocation in
  ``packages/docintel-eval/src/docintel_eval/runner.py`` (lines 107-145).
* ``tests/test_eval_determinism.py`` — the deferred-import xfail-strict
  convention against ``docintel_eval.runner``.
* 12-PATTERNS.md §"NEW (conditional) tests/test_eval_traces.py" (lines 377-379).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.xfail(strict=True, reason="Phase 12: Settings.trace_dir (12-02) + eval per-question TraceSpanCollector (D-02/A3) not yet wired")
def test_eval_run_writes_traces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """V-08 (A3) — an eval run populates trace_dir with one record per question.

    Drive ``run_eval`` in stub mode against a ``tmp_path`` ``trace_dir`` and the
    real ground-truth question set. Assert exactly one consolidated trace record
    per question lands under ``trace_dir`` and each line is valid JSON carrying
    the trace-record shape (``trace_id`` + ``spans``). Counts + shape only — no
    exact ms (RESEARCH A4).
    """
    from docintel_core.config import Settings
    from docintel_eval.dataset import load_questions
    from docintel_eval.runner import run_eval

    monkeypatch.setenv("DOCINTEL_LLM_PROVIDER", "stub")

    # trace_dir is a Settings field added in Plan 12-02 — raises until then
    # (the strict-xfail trigger). Keep eval report output inside tmp_path too.
    cfg = Settings(llm_provider="stub", trace_dir=str(tmp_path / "traces"))

    n_questions = len(load_questions(Path("data/eval/ground_truth/questions.jsonl")))

    rc = run_eval(cfg, output_dir=tmp_path / "reports")
    assert rc == 0

    trace_files = list((tmp_path / "traces").glob("*.jsonl"))
    assert trace_files, "A3: an eval run must populate trace_dir with trace records"

    records: list[dict] = []
    for tf in trace_files:
        for line in tf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))  # each line must be valid JSON

    assert len(records) == n_questions, (
        f"A3: expected one trace record per question ({n_questions}); got {len(records)}"
    )
    # Shape/presence only — every record carries a trace_id and an ordered spans list.
    for rec in records:
        assert isinstance(rec.get("trace_id"), str) and rec["trace_id"]
        assert isinstance(rec.get("spans"), list)
