"""Positive escape-hatch fixture for tests/test_check_before_sleep_safe.py::test_gate_passes_on_positive_fixture.

This file contains the D-06 positive shape — an ``@retry(`` decorator that
imports ``before_sleep_safe`` from ``docintel_core.adapters.real._logging``
and uses it as the ``before_sleep`` callback. The EMP-05 D-06 gate
(``scripts/check_before_sleep_safe.sh``, lands in Plan 14-04) must NOT flag
this file — it exits 0.

For EMP-05 the "positive side" is not a per-line escape-hatch (like the
no-print gate's ``# noqa: no-print``) but the D-06 structural positive
shape — a file that contains ``@retry(`` AND imports ``before_sleep_safe``
(D-06 side B). The gate's two-sided assertion (1) finds no raw
``before_sleep_log`` and (2) every ``@retry(``-using file imports
``before_sleep_safe`` — both pass here.

The planted ``@retry(... before_sleep=before_sleep_safe(...))`` IS the
entire reason this fixture exists — DO NOT remove it.

DO NOT import this file or execute it — it is a static fixture only.

This fixture is the analog of
``tests/fixtures/no_print_violations_with_noqa/allowed.py`` (the OBS-03
positive escape-hatch sibling convention adopted for EMP-05).
"""

import logging  # noqa: F401  # held by the fixture for parity with adapters/real

from tenacity import retry

# D-06 side B: the file containing @retry(  also imports before_sleep_safe
# from the canonical ._logging module. Plan 14-03 lands the helper; this
# import will fail at Wave 0 until then (the gate is text-only so its
# returncode is unaffected by an import-time failure of this file —
# the gate never imports it).
from docintel_core.adapters.real._logging import before_sleep_safe


@retry(before_sleep=before_sleep_safe(logging.getLogger(__name__), logging.WARNING))
def _safe() -> None:
    """Planted positive — the gate must accept this @retry( + before_sleep_safe pair."""
    ...
