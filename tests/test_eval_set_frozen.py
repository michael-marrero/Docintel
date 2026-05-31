"""Wave-0 xfail-strict scaffold — EMP-04 eval-set SHA256 freeze.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red test BEFORE the
production work in 14-02 ships. The constant ``EVAL_SET_SHA256`` is hardcoded
at module-scope per CONTEXT.md D-02 (mirrors the existing CI grep-gate
constant convention). Plan 14-02 renames the ground-truth dataset to
``eval_set.jsonl`` (CONTEXT.md D-01) and backfills the actual 64-char hex
digest into the placeholder.

Mutation policy (CONTEXT.md D-03):
  1. New ADR in DECISIONS.md documenting why
  2. Update ``EVAL_SET_SHA256`` below to the new digest
  3. Re-run real-eval to produce a fresh ``representative: true`` report
  4. Update ``data/eval/baseline.json`` per D-07

Lifecycle: this file is xfail-strict in Wave 0 (Plan 14-01) while the
renamed dataset does not yet exist on disk. Plan 14-02 lands the rename +
backfills the constant. A passing xfail-strict is an XPASS that fails the
suite, so 14-02 also removes the xfail marker in the same plan.

Analogs:
* ``tests/test_eval_dataset_schema.py:28-32, 139-144`` — path-anchor +
  exists-assertion conventions used by every Phase 8/10 eval test.
* 14-PATTERNS.md §"NEW tests/test_eval_set_frozen.py" (verbatim body from
  14-RESEARCH.md Pattern 3 lines 405-445).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-level path anchor (mirrors tests/test_eval_dataset_schema.py:32)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_SET_PATH = _REPO_ROOT / "data" / "eval" / "ground_truth" / "eval_set.jsonl"

# D-02: hardcoded constant at module-scope; mutation requires ADR per D-03.
# Plan 14-02 backfills the actual 64-char hex digest of the renamed dataset.
EVAL_SET_SHA256 = "<TO_BE_FILLED_IN_AT_FREEZE_TIME>"  # frozen Phase 14; mutation requires ADR per D-03


@pytest.mark.xfail(
    strict=True,
    reason="xfail until 14-02: D-01 rename to eval_set.jsonl + EVAL_SET_SHA256 backfill",
)
def test_eval_set_sha256_matches_frozen_constant() -> None:
    """EMP-04 / D-02: the eval set file must be byte-identical to its frozen SHA256.

    Wave-0 lands this red — both because the renamed file does not yet
    exist (D-01 rename is in Plan 14-02) AND because the placeholder above
    cannot match any real digest. Plan 14-02 performs the rename, sums the
    file once, pastes the digest into ``EVAL_SET_SHA256`` above, and removes
    the xfail marker in the same plan so an XPASS does not silently fail
    the suite.
    """
    assert _EVAL_SET_PATH.exists(), (
        f"EMP-04: eval_set.jsonl must exist at {_EVAL_SET_PATH}. "
        "If you renamed it, update _EVAL_SET_PATH per D-01."
    )
    actual = hashlib.sha256(_EVAL_SET_PATH.read_bytes()).hexdigest()
    assert actual == EVAL_SET_SHA256, (
        f"EMP-04: SHA256 mismatch — file mutated without ADR.\n"
        f"  Expected: {EVAL_SET_SHA256}\n"
        f"  Actual:   {actual}\n"
        f"Per D-03, mutations require: (1) ADR; (2) update EVAL_SET_SHA256; "
        f"(3) re-run real-eval; (4) update data/eval/baseline.json per D-07."
    )
