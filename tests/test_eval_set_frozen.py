"""EMP-04 eval-set SHA256 freeze — DECISIONS.md ADR-013 enforcement gate.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) landed this test with an
xfail-strict marker + ``<TO_BE_FILLED_IN_AT_FREEZE_TIME>`` placeholder while
the source dataset still lived at the pre-rename path. Plan 14-02 performed
the D-01 ``git mv`` to ``eval_set.jsonl``, backfilled the actual 64-char
hex digest of the renamed file into ``EVAL_SET_SHA256``, and removed the
xfail marker so the test runs green and any future byte-level mutation
fails CI loudly.

Mutation policy (DECISIONS.md ADR-013 / CONTEXT.md D-03): any future change
to ``eval_set.jsonl`` requires the documented 4-step protocol —
  1. A new ADR in DECISIONS.md documenting why
  2. Update ``EVAL_SET_SHA256`` below to the new digest
  3. Re-run real-eval to produce a fresh ``representative: true`` report
  4. Update ``data/eval/baseline.json`` per D-07

Analogs:
* ``tests/test_eval_dataset_schema.py:28-32, 139-144`` — path-anchor +
  exists-assertion conventions used by every Phase 8/10 eval test.
* 14-PATTERNS.md §"NEW tests/test_eval_set_frozen.py" (verbatim body from
  14-RESEARCH.md Pattern 3 lines 405-445).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level path anchor (mirrors tests/test_eval_dataset_schema.py:32)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_SET_PATH = _REPO_ROOT / "data" / "eval" / "ground_truth" / "eval_set.jsonl"

# D-02: hardcoded constant at module-scope; mutation requires ADR per D-03.
# Plan 14-02 backfills the actual 64-char hex digest of the renamed dataset.
EVAL_SET_SHA256 = "5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82"  # frozen Phase 14; mutation requires ADR per D-03


def test_eval_set_sha256_matches_frozen_constant() -> None:
    """EMP-04 / D-02: the eval set file must be byte-identical to its frozen SHA256.

    Plan 14-02 backfilled the digest above to the actual sha256 of the
    renamed ``data/eval/ground_truth/eval_set.jsonl`` (D-01) and removed the
    xfail marker so any future byte-level mutation surfaces as a CI fail
    pointing at DECISIONS.md ADR-013's 4-step mutation policy.
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
