"""Positive escape-hatch fixture for tests/test_prompt_locality.py::test_grep_gate_respects_noqa.

This file contains an inline prompt-like string identical to the negative
fixture (tests/fixtures/prompt_locality_violations/offender.py) but the
offending line carries the per-line escape-hatch comment defined in D-05.
The GEN-01 grep gate (scripts/check_prompt_locality.sh, Plan 06-02) must
NOT flag this file (exit code 0).

The triple-quoted body is a single-line string so the ``sed -n "${lineno}p"``
check inside the gate script fires on the same line as the offending
content (Plan 06-02 implementation note).

DO NOT import this file or execute it — it is a static fixture only.
"""

_INLINE_SYNTHESIS_PROMPT = """You are answering a question using ONLY the retrieved 10-K excerpts in the <context> block. Every factual sentence must end with a [chunk_id] citation."""  # noqa: prompt-locality
