"""Plan 12-01 Wave 0 xfail-strict scaffold for the OBS-03 no-print CI grep gate.

Covers 12-VALIDATION.md rows V-09..V-11 — the print-ban gate that Plan 12-03
ships in ``scripts/check_no_print.sh`` (the 5th CI grep gate, wired after
``check_prompt_locality`` per D-08). The three test functions exercise the
bash gate against:

* test_gate_fails_on_planted_print (V-09) — scan
  ``tests/fixtures/no_print_violations`` (the negative fixture). Its
  ``offender.py`` carries a single bare ``print(`` with NO ``# noqa: no-print``
  escape. The gate MUST catch it and exit non-zero.
* test_gate_passes_on_canonical_src (V-10) — run the gate with NO SCAN_DIR arg
  (defaults to the ``packages/*/src`` trees, D-06). Must exit 0. This only
  passes after Plan 12-03 rewords the comment example at
  ``adapters/real/qdrant_dense.py:83`` to drop the literal ``print(`` (D-07) —
  hence xfail now.
* test_gate_respects_noqa (V-11) — scan
  ``tests/fixtures/no_print_violations_with_noqa`` (the positive escape-hatch
  fixture). Its ``allowed.py`` carries the SAME bare ``print(`` plus a trailing
  ``# noqa: no-print``. The gate's per-line ``sed | grep '# noqa: no-print'``
  check must silence it and the gate must exit 0.

Lifecycle: these were scaffolded xfail-strict in Wave 0 (Plan 12-01, project
xfail-first convention, Phases 6-11) while ``scripts/check_no_print.sh`` did not
yet exist. Plan 12-03 ships the gate + rewords ``qdrant_dense.py:83``, so the
xfail markers were removed in the same plan (a passing xfail-strict is an XPASS,
which fails the suite). V-09..V-11 now assert green directly.

Analogs:
* ``tests/test_prompt_locality.py`` — the verbatim gate-test convention
  (``_REPO_ROOT`` / ``_GATE_SCRIPT`` / ``_*_FIXTURE_DIR`` module constants +
  ``subprocess.run(["bash", script, SCAN_DIR])`` + the positive/negative/noqa
  trio).
* ``tests/test_ci_gates.py`` — the SCAN_DIR-arg negative-case convention.
* 12-PATTERNS.md §"NEW tests/test_no_print_gate.py" (lines 339-367).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_no_print.sh"
_NEG_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "no_print_violations"
_NOQA_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "no_print_violations_with_noqa"


def test_gate_fails_on_planted_print() -> None:
    """V-09 — gate exits non-zero against the planted bare ``print(`` (no escape).

    Invokes the gate with ``tests/fixtures/no_print_violations`` as the SCAN_DIR
    argument. The fixture's ``offender.py`` contains a single bare ``print(``
    with no ``# noqa: no-print`` escape — exactly what the OBS-03 gate scans for.
    The gate MUST catch it and exit non-zero.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_NEG_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "OBS-03 gate did not catch the planted bare print(. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_passes_on_canonical_src() -> None:
    """V-10 — scanning ``packages/*/src`` (no SCAN_DIR arg) exits 0 once 12-03 lands.

    Plan 12-03 ships ``scripts/check_no_print.sh`` (default-scan over every
    ``packages/*/src`` tree, D-06) and rewords the comment example at
    ``adapters/real/qdrant_dense.py:83`` to drop the literal ``print(`` (D-07).
    Once those land, the gate exits 0 on the clean canonical src trees. This
    test is the final acceptance for the Plan 12-05 xfail-removal sweep.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "OBS-03 gate flagged the canonical packages/*/src trees. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_respects_noqa() -> None:
    """V-11 — D-07 per-line ``# noqa: no-print`` escape hatch.

    Invokes the gate with ``tests/fixtures/no_print_violations_with_noqa`` as
    the SCAN_DIR argument. The fixture's ``allowed.py`` carries the SAME bare
    ``print(`` as the negative fixture BUT with a trailing ``# noqa: no-print``.
    The gate's ``sed -n "${lineno}p" | grep '# noqa: no-print'`` check must
    silence that line and the gate must exit 0.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_NOQA_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "OBS-03 gate flagged a line carrying `# noqa: no-print`. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
