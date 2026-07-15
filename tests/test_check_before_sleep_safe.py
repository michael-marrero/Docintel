"""Wave-0 xfail-strict scaffold — EMP-05 D-06 ``check_before_sleep_safe.sh`` gate trio.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red trio BEFORE
``scripts/check_before_sleep_safe.sh`` ships in Plan 14-04. The CI grep gate
is two-sided per CONTEXT.md D-06:

  1. ``grep -r 'before_sleep_log' adapters/real/`` returns nothing.
  2. Every file in ``adapters/real/`` containing ``@retry(`` MUST also
     import ``before_sleep_safe`` from ``._logging``.

Trio shape mirrors ``tests/test_no_print_gate.py:43-111`` verbatim — the
established project convention for every CI grep gate (3 functions:
negative-fixture / canonical-scan / positive-fixture). The negative fixture
sits at ``tests/fixtures/before_sleep_violations/_unsafe_example.py`` (the
leading underscore matches the gate's path filter so the canonical scan
never trips on it). The positive fixture sits at
``tests/fixtures/before_sleep_violations_with_safe/safe_example.py``.

Lifecycle:
* test_gate_fails_on_planted_raw_before_sleep_log (negative) — xfail-strict
  until 14-04 ships ``scripts/check_before_sleep_safe.sh`` (the test fails
  today because the gate script does not exist).
* test_gate_passes_on_canonical_adapters_real (canonical) — xfail-strict
  until 14-04 sweeps the 12 use-sites across 6 files (RESEARCH Pitfall 1
  corrected the original CONTEXT.md D-04 undercount of "6 across 5"). Today
  the canonical ``adapters/real/`` tree contains 12 raw
  ``before_sleep=before_sleep_log(...)`` lines so the gate will exit
  non-zero.
* test_gate_passes_on_positive_fixture (positive) — xfail-strict until
  14-04 ships the gate script. Once the script lands and the sweep
  completes, the positive fixture (containing an ``@retry(`` that imports
  ``before_sleep_safe`` from ``._logging``) must exit 0.

Analogs:
* ``tests/test_no_print_gate.py:43-111`` — verbatim trio shape.
* ``tests/test_index_wraps_gate.py:33-83`` — subprocess.run + ``check_*``
  gate convention.
* 14-PATTERNS.md §"NEW tests/test_check_before_sleep_safe.py" (verbatim
  body, mirrors the no-print trio).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_before_sleep_safe.sh"
_NEG_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "before_sleep_violations"
_POS_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "before_sleep_violations_with_safe"
)


def test_gate_fails_on_planted_raw_before_sleep_log() -> None:
    """EMP-05 / D-06 (negative) — gate exits non-zero against the planted raw ``before_sleep_log``.

    Invokes the gate with ``tests/fixtures/before_sleep_violations`` as the
    SCAN_DIR argument. The fixture's ``_unsafe_example.py`` contains
    ``@retry(before_sleep=before_sleep_log(...))`` directly — exactly what
    the D-06 gate scans for. The gate MUST catch it and exit non-zero. The
    leading underscore on the fixture filename matches the gate's path
    filter so the canonical scan (no SCAN_DIR arg) never trips on it.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_NEG_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "EMP-05 / D-06 gate did not catch the planted raw before_sleep_log. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_passes_on_canonical_adapters_real() -> None:
    """EMP-05 / D-06 (canonical) — gate exits 0 scanning ``adapters/real/`` after the sweep.

    Invokes the gate with NO SCAN_DIR argument (defaults to
    ``packages/docintel-core/src/docintel_core/adapters/real/`` per D-06).
    Plan 14-04 sweeps all 12 ``before_sleep=before_sleep_log(...)`` use
    sites across 6 files (qdrant_dense ×6, judge ×2, llm_anthropic /
    llm_openai / embedder_bge / reranker_bge ×1 each) to
    ``before_sleep_safe(...)``. Once that sweep lands, every file
    containing ``@retry(`` also imports ``before_sleep_safe`` (D-06 side B)
    and the gate exits 0.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "EMP-05 / D-06 gate flagged the canonical adapters/real/ tree. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_passes_on_positive_fixture() -> None:
    """EMP-05 / D-06 (positive) — gate exits 0 on the planted positive fixture.

    Invokes the gate with ``tests/fixtures/before_sleep_violations_with_safe``
    as the SCAN_DIR argument. The fixture's ``safe_example.py`` contains
    ``@retry(before_sleep=before_sleep_safe(...))`` AND
    ``from docintel_core.adapters.real._logging import before_sleep_safe``
    — exactly what the D-06 positive side asserts. The gate MUST accept it
    and exit 0.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_POS_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "EMP-05 / D-06 gate rejected a properly-wrapped before_sleep_safe fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
