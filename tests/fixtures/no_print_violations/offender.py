"""Negative fixture for tests/test_no_print_gate.py::test_gate_fails_on_planted_print.

This file intentionally contains a single **bare** ``print(`` call outside the
``# noqa: no-print`` escape hatch. The OBS-03 print gate
(``scripts/check_no_print.sh``, lands in Plan 12-03) must flag this file and
exit non-zero.

The planted ``print(`` IS the entire reason this fixture exists — do NOT remove
it. The repo's ruff config does NOT select flake8-print (T201 is not in
``select = ["E","F","I","B","UP","RUF"]``), so a bare ``print(`` passes
pre-commit cleanly with no noqa needed (cf. ``scripts/measure_tokenizer_drift.py``,
which prints without any suppression). This line deliberately carries NO
``# noqa: no-print`` escape, so the OBS-03 gate must catch it.

The print gate scans ``packages/*/src`` only (D-06), never ``tests/`` — so this
fixture never trips the real CI gate; the negative-case test invokes the gate
with this directory as an explicit SCAN_DIR argument.

DO NOT import this file or execute it — it is a static fixture only:

* pytest does NOT collect it (lives under tests/fixtures/, filename does not
  start with test_, no pytest-collectable construct inside).

This fixture is the analog of ``tests/fixtures/prompt_locality_violations/offender.py``
(the GEN-01 negative-case dir-of-one-offender convention).
"""

print("offending line")
