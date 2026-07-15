"""Wave-0 xfail-strict scaffold — EMP-03 / D-11 hero.gif presence + mtime check.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red test BEFORE
the user records ``docs/hero.gif`` per ``docs/HERO-STORYBOARD.md``. Per
CONTEXT.md D-11, hero recording is user-owned and happens AFTER
``data/eval/baseline.json`` is committed — so the test asserts both that
the file exists AND that its mtime is strictly newer than ``baseline.locked_at``
(ordering invariant).

CONTEXT.md D-11 + 14-RESEARCH "Anti-Patterns to Avoid": do NOT commit a
1×1 placeholder ``hero.gif`` — the presence check IS the gate. The
EMPIRICAL-PENDING status is the honest signal that the work is still
user-owned.

Lifecycle: xfail-strict PERMANENTLY until the user records the GIF per the
checklist at ``docs/REAL-RUN-CHECKLIST.md``. The xfail reason explicitly
references "EMPIRICAL-PENDING D-11" so Plan 14-07 (phase-gate) can grep
for the marker and report the still-pending status honestly. Plan 14-07
does NOT remove this xfail marker (mirrors Phase 5
``test_reranker_canary_real_mode`` EMPIRICAL-PENDING precedent — the
marker is removed by a human PR after the artifact lands).

Analogs:
* ``tests/test_docs_gates.py:16-35`` — repo-root walk + presence-check
  shape (``decisions.is_file()``).
* 14-PATTERNS.md §"NEW tests/test_hero_gif_present.py" (presence + mtime
  > baseline.locked_at convention).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """Walk up from this file to the dir containing ``pyproject.toml`` / ``.git``.

    Verbatim from ``tests/test_docs_gates.py:16-26``.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return here.parents[1]


@pytest.mark.xfail(
    strict=True,
    reason="EMPIRICAL-PENDING D-11: user records docs/hero.gif AFTER baseline.json lock per docs/REAL-RUN-CHECKLIST.md (Phase 14 phase-gate preserves this marker per Phase 5 precedent)",
)
def test_hero_gif_present_and_newer_than_baseline() -> None:
    """EMP-03 / D-11: ``docs/hero.gif`` exists, has non-zero size, and mtime > baseline.locked_at.

    Three assertions:
      (a) ``(_repo_root() / "docs" / "hero.gif").is_file()`` — user
          recorded the GIF.
      (b) ``stat().st_size > 0`` — the file is not a 0-byte placeholder.
      (c) ``datetime.fromtimestamp(mtime, tz=utc) > baseline.locked_at`` —
          the recording happened AFTER baseline lock (D-11 ordering
          invariant; ensures the storyboard reflects the baseline numbers).

    The ``locked_at`` parse uses ``.replace("Z", "+00:00")`` so Python 3.11
    ``datetime.fromisoformat`` accepts the canonical ISO-8601 ``Z`` suffix.
    """
    hero = _repo_root() / "docs" / "hero.gif"
    baseline_json = _repo_root() / "data" / "eval" / "baseline.json"

    assert hero.is_file(), (
        f"EMP-03 / D-11: docs/hero.gif missing at {hero}. "
        "Record per docs/HERO-STORYBOARD.md AFTER `make baseline-lock` "
        "commits data/eval/baseline.json."
    )
    assert hero.stat().st_size > 0, (
        f"EMP-03 / D-11: docs/hero.gif is empty at {hero}. "
        "RESEARCH Anti-Pattern: do NOT commit a 1×1 placeholder — the "
        "presence check IS the gate."
    )

    assert baseline_json.is_file(), (
        f"EMP-03 / D-11: data/eval/baseline.json missing at {baseline_json}. "
        "Hero GIF mtime ordering requires baseline.locked_at; lock the "
        "baseline first via `make baseline-lock TS=<ts>`."
    )
    baseline_payload = json.loads(baseline_json.read_text("utf-8"))
    locked_at_raw = baseline_payload["locked_at"]
    locked_at = datetime.fromisoformat(locked_at_raw.replace("Z", "+00:00"))

    hero_mtime = datetime.fromtimestamp(hero.stat().st_mtime, tz=timezone.utc)
    assert hero_mtime > locked_at, (
        f"EMP-03 / D-11: docs/hero.gif mtime ({hero_mtime.isoformat()}) is "
        f"NOT strictly newer than baseline.locked_at ({locked_at.isoformat()}). "
        "Re-record the GIF AFTER `make baseline-lock` commits."
    )
