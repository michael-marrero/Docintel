"""Stub-run determinism regression for Phase 10 (D-12).

Wave-0 semantics (Plan 10-01): the single test here is scaffolded as
xfail(strict=True) against the not-yet-implemented docintel_eval.runner
module. The import of run_eval is deferred into the test body so
collection never crashes before Wave 1 ships the implementation.

Regression contract pinned by this test:
  - run_eval must accept an output_dir keyword argument (Wave 1 contract)
    so two runs can be written to separate directories and compared.
  - Two successive stub runs with the same fixed seeds (bootstrap seed=42,
    deterministic stub adapters) must produce bit-exact equal per_question
    lists — same question IDs, same metric values, same ordering.

This property ensures that the CI validate gate's determinism assertion
(D-11 / D-12) holds: a re-run on the same input always yields the same
output, so validate can be called independently of the original run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-level path anchor (standard project convention)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# D-12: stub run determinism — two in-process runs produce identical per_question
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run_eval lands in Wave 1",
)
def test_stub_run_deterministic(tmp_path: Path) -> None:
    """D-12: two stub runs with the same seed produce identical per_question values.

    Calls run_eval twice into separate output directories, loads both
    results.json files, and asserts per_question lists are bit-exact equal.

    This pins two Wave 1 contracts simultaneously:
      1. run_eval(cfg, output_dir=<path>) — the output_dir keyword is required
         so the harness can write two runs without colliding on a timestamp dir.
      2. Stub determinism — fixed seeds (bootstrap seed=42, deterministic stub
         adapters) must produce identical per_question rows across two calls
         (D-12; validated in the EVAL-04 CI gate via docintel-eval validate).
    """
    from docintel_core.config import Settings  # type: ignore[import-not-found]
    from docintel_eval.runner import run_eval  # type: ignore[import-not-found]

    cfg = Settings()

    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    run_eval(cfg, output_dir=dir_a)
    run_eval(cfg, output_dir=dir_b)

    results_a = json.loads((dir_a / "results.json").read_text(encoding="utf-8"))
    results_b = json.loads((dir_b / "results.json").read_text(encoding="utf-8"))

    assert results_a["per_question"] == results_b["per_question"], (
        "D-12: stub run must be deterministic — per_question values must be "
        "bit-exact equal across two runs with the same fixed seeds. "
        "Check that bootstrap seed=42 is wired through and stub adapters are "
        "deterministic (no random state leaking between calls)."
    )
