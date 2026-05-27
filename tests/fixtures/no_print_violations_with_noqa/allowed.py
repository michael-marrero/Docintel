"""Positive escape-hatch fixture for tests/test_no_print_gate.py::test_gate_respects_noqa.

This file contains the SAME bare ``print(`` line as the negative fixture
(tests/fixtures/no_print_violations/offender.py) but the offending line carries
the per-line escape-hatch comment ``# noqa: no-print`` defined in D-07. The
OBS-03 print gate (``scripts/check_no_print.sh``, lands in Plan 12-03) must NOT
flag this line — it exits 0.

The gate's ``sed -n "${lineno}p" | grep '# noqa: no-print'`` check fires on the
same line as the offending ``print(``, so the escape silences it (mirroring
``scripts/check_prompt_locality.sh``'s ``# noqa: prompt-locality`` handling).

Ruff emits a benign "Invalid # noqa directive" warning for ``no-print`` (it is
the gate's tag, not a ruff code) but still passes — identical behaviour to the
existing ``tests/fixtures/prompt_locality_violations_with_noqa/allowed.py``
sibling, which carries ``# noqa: prompt-locality``.

DO NOT import this file or execute it — it is a static fixture only.

This fixture is the analog of
``tests/fixtures/prompt_locality_violations_with_noqa/allowed.py`` (the GEN-01
positive escape-hatch sibling convention).
"""

print("offending line")  # noqa: no-print
