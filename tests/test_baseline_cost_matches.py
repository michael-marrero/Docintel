"""Wave-0 xfail-strict scaffold — EMP-01 / D-09 cost_usd sum cross-check.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red test BEFORE
``data/eval/baseline.json`` exists. D-09 locks ``cost_usd`` granularity =
single per-eval-run total USD across the frozen 32-record set; this test
asserts the value the user records in ``baseline.json`` matches the
underlying report's ``manifest.total_cost_usd`` AND the sum of per-question
``cost_usd`` values — three numbers that must agree (modulo float
roundoff).

Source shape (14-RESEARCH.md lines 686-737 + runner.py:218-243, 338-356):

  per-question:  result.completion.cost_usd (float)
  manifest:      total_cost_usd = sum(t.cost_usd for t in timings)
  baseline.json: cost_usd (extracted by `make baseline-lock` from results.json)

Lifecycle: xfail-strict in Wave 0 (Plan 14-01) while ``baseline.json``
does not yet exist. Plan 14-05 lands ``make baseline-lock``; the user runs
it once. The marker is removed in 14-06 (or preserved per EMPIRICAL-PENDING
precedent — plan determines).

Analogs:
* ``tests/test_index_manifest.py:69-88`` — load tracked JSON, cross-reference
  recorded value with computed value, assert equality (the exact role-match).
* 14-PATTERNS.md §"NEW tests/test_baseline_cost_matches.py" (D-09 sum
  cross-check shape).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / "data" / "eval" / "baseline.json"


@pytest.mark.xfail(
    strict=True,
    reason="xfail until 14-06: user runs `make baseline-lock` (cost_usd cross-check requires baseline.json + results.json)",
)
def test_baseline_cost_matches_manifest_and_per_question_sum() -> None:
    """EMP-01 / D-09: baseline.cost_usd == manifest.total_cost_usd == sum(per-question cost_usd).

    Loads ``data/eval/baseline.json`` to get ``report_dir`` + ``cost_usd``.
    Opens ``<report_dir>/results.json`` and pulls (a) ``manifest.total_cost_usd``
    and (b) ``sum(q["cost_usd"] for q in per_question)``. All three values
    must agree to ``pytest.approx(abs=1e-6)`` — the float-roundoff
    tolerance recommended by 14-RESEARCH "Don't Hand-Roll" row.
    """
    assert _BASELINE_PATH.is_file(), (
        f"EMP-01 / D-07: data/eval/baseline.json missing at {_BASELINE_PATH}. "
        "Plan 14-05 lands `make baseline-lock`; user runs it once after "
        "the real-eval workflow commits a representative report."
    )
    baseline = json.loads(_BASELINE_PATH.read_text("utf-8"))

    baseline_cost = baseline["cost_usd"]
    report_dir = _REPO_ROOT / baseline["report_dir"]
    results_path = report_dir / "results.json"

    assert results_path.is_file(), (
        f"D-09: report results.json missing at {results_path}. "
        f"baseline.json points at {baseline['report_dir']!r}."
    )
    results = json.loads(results_path.read_text("utf-8"))

    manifest_total = results["manifest"]["total_cost_usd"]
    per_question = results.get("per_question", [])
    per_question_sum = sum(q["cost_usd"] for q in per_question)

    assert baseline_cost == pytest.approx(manifest_total, abs=1e-6), (
        f"D-09: baseline.cost_usd ({baseline_cost}) does not match "
        f"manifest.total_cost_usd ({manifest_total}) — drift between "
        f"`make baseline-lock` extraction and the report manifest."
    )
    assert manifest_total == pytest.approx(per_question_sum, abs=1e-6), (
        f"D-09: manifest.total_cost_usd ({manifest_total}) does not match "
        f"sum(per_question.cost_usd) ({per_question_sum}) — drift between "
        f"the per-question telemetry and the manifest sum."
    )
