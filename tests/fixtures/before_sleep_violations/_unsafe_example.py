"""Negative fixture for tests/test_check_before_sleep_safe.py::test_gate_fails_on_planted_raw_before_sleep_log.

This file intentionally contains a single **raw** ``before_sleep=before_sleep_log(``
use-site outside any redaction wrapper. The EMP-05 D-06 gate
(``scripts/check_before_sleep_safe.sh``, lands in Plan 14-04) must flag this
file and exit non-zero.

The planted ``before_sleep=before_sleep_log(`` IS the entire reason this
fixture exists — DO NOT remove it. The repo's ruff config does not select
a rule that catches this pattern (the gate scans for the literal string),
so the file passes pre-commit cleanly with no noqa needed. This line
deliberately carries NO escape comment, so the EMP-05 D-06 gate must catch
it.

The before-sleep-safe gate scans
``packages/docintel-core/src/docintel_core/adapters/real/`` only (D-06),
never ``tests/`` — so this fixture never trips the real CI gate; the
negative-case test invokes the gate with this directory as an explicit
SCAN_DIR argument.

The filename carries a leading underscore so that even if the gate is
broadened to a recursive ``--include="*.py"`` scan, the canonical
adapters/real path filter skips this file (mirrors
``tests/fixtures/no_print_violations/offender.py``'s sibling convention
where the offender lives outside the gate's default scan domain).

DO NOT import this file or execute it — it is a static fixture only:

* pytest does NOT collect it (lives under tests/fixtures/, filename starts
  with an underscore, no pytest-collectable construct inside).

This fixture is the analog of ``tests/fixtures/no_print_violations/offender.py``
(the OBS-03 negative-case dir-of-one-offender convention adopted for EMP-05).
"""

# Imports just enough for the symbol to be present at file-scope (the D-06
# grep is text-only — it scans for the literal string ``before_sleep_log``
# without distinguishing import-context vs decorator-arg-context).
import logging  # noqa: F401  # held by the fixture for parity with adapters/real

from tenacity import before_sleep_log, retry


@retry(before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING))
def _unsafe() -> None:
    """Planted violation — the gate must flag the line above."""
    ...
