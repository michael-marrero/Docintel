"""Wave-0 xfail-strict scaffold — EMP-01 / D-07 baseline.json 7-field schema validation.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red test BEFORE
Plan 14-05 ships the ``make baseline-lock`` Makefile target and the user
runs it (per CONTEXT.md D-08, baseline locking is a two-step process: CI
produces the report; the user runs the make target after eyeballing it).
Both the test file and the validation it asserts depend on
``data/eval/baseline.json`` existing on disk.

D-07 schema (verbatim from CONTEXT.md D-07):

.. code-block:: json

    {
      "report_dir": "data/eval/reports/<ts>/",
      "git_sha": "<40-char-sha>",
      "eval_set_sha256": "<64-char-sha>",
      "prompt_version_hash": "<12-char-hash>",
      "phase_locked": 14,
      "cost_usd": <float>,
      "locked_at": "<ISO-8601>"
    }

Lifecycle: xfail-strict in Wave 0 (Plan 14-01) while
``data/eval/baseline.json`` does not yet exist. Plan 14-05 lands the
``make baseline-lock`` target; the user runs it once after eyeballing the
real-eval report. An XPASS would then fail the suite, so Plan 14-06
removes the xfail marker after the user owns the lock step (or 14-07 if
the marker is preserved per Phase 5 ``test_reranker_canary_real_mode``
EMPIRICAL-PENDING precedent — plan determines).

Analogs:
* ``tests/test_index_manifest.py:32-67`` — load tracked JSON, assert
  per-field invariants (the exact role-match: tracked JSON pointer file,
  schema-tested in pytest).
* 14-PATTERNS.md §"NEW tests/test_baseline_schema.py" (verbatim body
  shape, D-07 7-field schema).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / "data" / "eval" / "baseline.json"

# D-07 7-field schema — every key must be present.
_D07_REQUIRED_FIELDS: tuple[str, ...] = (
    "report_dir",
    "git_sha",
    "eval_set_sha256",
    "prompt_version_hash",
    "phase_locked",
    "cost_usd",
    "locked_at",
)


def test_baseline_schema_validates() -> None:
    """EMP-01 / D-07: ``data/eval/baseline.json`` validates against the 7-field schema.

    Asserts every D-07 field is present, ``phase_locked == 14`` (the v1.0
    baseline identity anchor), and the value types match the schema
    (int / float / str). The ``locked_at`` field must parse as ISO-8601
    via ``datetime.fromisoformat`` (with the canonical ``Z`` → ``+00:00``
    replacement so Python 3.11 stdlib accepts it). git_sha must be 40-char
    hex; eval_set_sha256 must be 64-char hex; prompt_version_hash must be
    12-char (Phase 6 GEN-02 convention).
    """
    assert _BASELINE_PATH.is_file(), (
        f"EMP-01 / D-07: data/eval/baseline.json missing at {_BASELINE_PATH}. "
        "Plan 14-05 lands `make baseline-lock`; user runs it once after "
        "the real-eval workflow commits a representative report."
    )
    manifest = json.loads(_BASELINE_PATH.read_text("utf-8"))

    for field in _D07_REQUIRED_FIELDS:
        assert field in manifest, (
            f"EMP-01 / D-07: baseline.json missing required field {field!r}. "
            f"Schema: {_D07_REQUIRED_FIELDS}."
        )

    # phase_locked: anchors v1.0 baseline identity; literal 14.
    assert isinstance(
        manifest["phase_locked"], int
    ), f"D-07: phase_locked must be int; got {type(manifest['phase_locked']).__name__}"
    assert manifest["phase_locked"] == 14, (
        f"D-07: phase_locked must equal 14 (v1.0 baseline anchor); "
        f"got {manifest['phase_locked']!r}"
    )

    # cost_usd: float (per-eval-run total USD; granularity locked by D-09).
    assert isinstance(
        manifest["cost_usd"], (int, float)
    ), f"D-07/D-09: cost_usd must be numeric; got {type(manifest['cost_usd']).__name__}"

    # git_sha: 40-char hex (canonical git object identifier).
    git_sha = manifest["git_sha"]
    assert (
        isinstance(git_sha, str) and len(git_sha) == 40
    ), f"D-07: git_sha must be 40-char string; got len={len(git_sha)}"
    assert all(
        c in "0123456789abcdef" for c in git_sha
    ), f"D-07: git_sha must be lowercase hex; got {git_sha!r}"

    # eval_set_sha256: 64-char hex (matches EVAL_SET_SHA256 constant in
    # tests/test_eval_set_frozen.py; cross-checked by Phase 17 deltas).
    eval_sha = manifest["eval_set_sha256"]
    assert (
        isinstance(eval_sha, str) and len(eval_sha) == 64
    ), f"D-07: eval_set_sha256 must be 64-char string; got len={len(eval_sha)}"

    # prompt_version_hash: 12-char (Phase 6 GEN-02 convention).
    prompt_hash = manifest["prompt_version_hash"]
    assert isinstance(prompt_hash, str) and len(prompt_hash) == 12, (
        f"D-07: prompt_version_hash must be 12-char string (Phase 6 GEN-02); "
        f"got len={len(prompt_hash)}"
    )

    # locked_at: ISO-8601 parseable; tolerate trailing "Z" → "+00:00" for
    # Python 3.11 stdlib.
    locked_at_raw = manifest["locked_at"]
    assert isinstance(
        locked_at_raw, str
    ), f"D-07: locked_at must be string; got {type(locked_at_raw).__name__}"
    try:
        datetime.fromisoformat(locked_at_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssertionError(
            f"D-07: locked_at must parse as ISO-8601; got {locked_at_raw!r} " f"(error: {exc})"
        ) from exc
