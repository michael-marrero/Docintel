"""Plan 06-01 Wave 0 xfail scaffolds for the GEN-01 prompt-locality grep gate.

Covers VALIDATION.md row 06-01-* (GEN-01 + D-04 + D-05) — the Phase 6
prompt-locality CI gate. The three test functions exercise the bash script
``scripts/check_prompt_locality.sh`` (lands in Plan 06-02) against:

* test_grep_gate_passes_on_canonical_layout — scan the production
  ``packages/`` tree with no arguments. Must exit 0 once Plan 06-03 ships
  ``packages/docintel-generate/src/docintel_generate/prompts.py`` and Plan
  06-05 syncs the stub adapter's ``_STUB_REFUSAL`` constant to the
  canonical sentinel. xfail until Plan 06-07's xfail-removal sweep.
* test_grep_gate_fails_on_violation — scan
  ``tests/fixtures/prompt_locality_violations`` (negative fixture from
  Task 0). Must exit non-zero — the planted inline prompt-like string is
  exactly what D-04's NAME_PATTERN + PHRASE_PATTERN scan for. xfail until
  Plan 06-02 ships the gate script.
* test_grep_gate_respects_noqa — scan
  ``tests/fixtures/prompt_locality_violations_with_noqa`` (positive
  escape-hatch fixture from Task 0). Must exit 0 — D-05's per-line
  ``# noqa: prompt-locality`` escape hatch must silence the gate. xfail
  until Plan 06-02 ships the gate's noqa handling.

The in-function ``bash scripts/check_prompt_locality.sh`` invocation
returns a non-zero return code under Wave 0 (the script does not exist
yet) — pytest counts this as the expected failure under xfail(strict=True).

Analogs:
* ``tests/test_index_wraps_gate.py`` (Phase 4 D-21 grep-gate analog —
  same _REPO_ROOT / _GATE_SCRIPT / _FIXTURE_DIR module constants +
  ``subprocess.run(["bash", ...])`` invocation shape).
* ``tests/test_ingest_wraps_gate.py`` (Phase 3 analog) and
  ``tests/fixtures/missing_tenacity/qdrant_fake.py`` (Phase 4 negative
  fixture analog).
* 06-PATTERNS.md §"CI grep-gate test pattern (positive + negative fixture)"
  lines 941-964.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_prompt_locality.sh"
_NEG_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "prompt_locality_violations"
_POS_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "prompt_locality_violations_with_noqa"
)


def test_grep_gate_passes_on_canonical_layout() -> None:
    """GEN-01 — scanning ``packages/`` (no SCAN_DIR arg) exits 0 once Waves 1-3 land.

    Plan 06-02 ships ``scripts/check_prompt_locality.sh`` with default-scan
    on ``packages/`` per D-04. Plan 06-03 lands ``prompts.py`` (allowlisted);
    Plan 06-05 syncs ``_STUB_REFUSAL`` to the canonical sentinel
    (allowlisted). Once those land, the gate exits 0 on a clean canonical
    layout. This test is the final acceptance for the Wave 4 xfail-removal
    sweep (Plan 06-07).
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "GEN-01 gate flagged the canonical packages/ layout. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_grep_gate_fails_on_violation() -> None:
    """GEN-01 — gate exits non-zero against the negative fixture (D-04 PHRASE_PATTERN).

    Invokes the gate with ``tests/fixtures/prompt_locality_violations`` as
    the SCAN_DIR argument. The fixture's ``offender.py`` contains an
    inline ``_INLINE_SYNTHESIS_PROMPT`` triple-quoted string matching the
    D-04 NAME_PATTERN (`_[A-Z_]*PROMPT[A-Z_]*\\b`) + at least three of the
    PHRASE_PATTERN substrings (``You are``, ``<context>``, ``cite``,
    ``chunk_id``). The gate MUST catch this and exit non-zero.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_NEG_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "GEN-01 gate did not catch the planted prompt-like inline string. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_grep_gate_respects_noqa() -> None:
    """GEN-01 — D-05 per-line ``# noqa: prompt-locality`` escape hatch.

    Invokes the gate with ``tests/fixtures/prompt_locality_violations_with_noqa``
    as the SCAN_DIR argument. The fixture's ``allowed.py`` carries the SAME
    offending shape as the negative fixture BUT with
    ``# noqa: prompt-locality`` appended to the offending line. The gate's
    ``sed -n "${lineno}p" | grep noqa`` check must silence the warning for
    that line and the gate must exit 0.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_POS_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "GEN-01 gate flagged a line carrying `# noqa: prompt-locality`. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
