"""Plan 06-01 Wave 0 xfail scaffolds for D-09 judge structured-output migration.

Covers VALIDATION.md row 06-05-* (D-09) — the Phase 2 → Phase 6 migration
of the cross-family judge:

* test_judge_returns_judgeverdict — REAL-MODE: structured-output dispatch
  (Anthropic ``tools=[{...}]`` or OpenAI ``response_format=
  {"type": "json_schema", ...}``) deserializes directly into
  ``JudgeVerdict`` with all four fields populated (score / passed /
  reasoning / unsupported_claims). Marker: ``@pytest.mark.real`` (OUTER)
  + the xfail-strict marker (INNER) — see analog.
* test_deserialization_failure_returns_sentinel — STUB-MOCKABLE: when the
  SDK call returns a payload that doesn't match the ``JudgeVerdict``
  schema, the result is a sentinel ``JudgeVerdict(score=0.0, passed=False,
  reasoning="<deserialization failed>", unsupported_claims=[])`` (per
  Pitfall 6 — failures are measurements, not retry triggers).

The real-mode test carries BOTH ``@pytest.mark.real`` (OUTER, deselected
by ``-m "not real"`` in CI) AND the xfail-strict marker (INNER,
preserved through Phase 6). The marker ORDERING is load-bearing —
pytest's marker-collection layer evaluates ``not real`` deselection
BEFORE applying the xfail, so the test is deselected from default CI
runs and only collected via ``-m real``.

Module-level ``pytestmark = pytest.mark.real`` is intentionally NOT
applied — that would gate the STUB-MOCKABLE deserialization test behind
the real-mode marker and break stub-CI (06-PATTERNS.md anti-pattern
flag at lines 868-869).

Analogs:
* ``tests/test_reranker_canary.py:test_reranker_canary_real_mode`` (lines
  350-406) — dual-mode marker pattern (function-level, not module-level);
  the docstring at lines 52-65 explains the rationale.
* ``tests/test_adapters.py:test_stub_judge_score_range`` (lines 123-135)
  — stub-judge verdict-shape assertion pattern.
* 06-PATTERNS.md §"Tests scaffolds" line 851 (analog assignment).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


@pytest.mark.real
@pytest.mark.xfail(strict=True, reason="Wave 3 — Plan 06-06 ships structured-output dispatch + JudgeVerdict deserializer")
def test_judge_returns_judgeverdict() -> None:
    """D-09 real-mode — structured-output dispatch deserializes into JudgeVerdict.

    Constructs a real-mode bundle (``llm_provider="real"`` +
    ``llm_real_provider="anthropic"``) and calls
    ``bundle.judge.judge(prediction, reference, rubric)``. Plan 06-06
    ships the structured-output migration: Anthropic ``tools=[{...}]``
    binds the response to the four-field JSON schema; OpenAI
    ``response_format={"type": "json_schema", ...}`` does the same. Both
    paths deserialize directly into ``JudgeVerdict`` — no more heuristic
    regex scrape.

    Costs real API credits; gated by ``@pytest.mark.real`` (deselected
    on every PR's default ``-m "not real"`` run; collected only in the
    ``real-index-build`` workflow_dispatch job).
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.types import JudgeVerdict
    from docintel_core.config import Settings

    bundle = make_adapters(Settings(llm_provider="real", llm_real_provider="anthropic"))
    verdict = bundle.judge.judge(
        prediction="Apple revenue grew.",
        reference=["Apple revenue grew."],
        rubric="",
    )
    assert isinstance(verdict, JudgeVerdict), (
        f"D-09: judge must return JudgeVerdict; got {type(verdict).__name__}"
    )
    assert 0.0 <= verdict.score <= 1.0, (
        f"D-09: JudgeVerdict.score must be in [0, 1]; got {verdict.score!r}"
    )
    assert isinstance(verdict.passed, bool), (
        f"D-09: JudgeVerdict.passed must be bool; got {type(verdict.passed).__name__}"
    )
    assert isinstance(verdict.reasoning, str), (
        f"D-09: JudgeVerdict.reasoning must be str; got {type(verdict.reasoning).__name__}"
    )
    assert isinstance(verdict.unsupported_claims, list), (
        f"D-09: JudgeVerdict.unsupported_claims must be list; "
        f"got {type(verdict.unsupported_claims).__name__}"
    )


def test_deserialization_failure_returns_sentinel() -> None:
    """D-09 + Pitfall 6 — deserialization failure returns a sentinel verdict.

    When the SDK returns a payload whose ``.input`` field doesn't match
    the four-field ``JudgeVerdict`` schema (e.g., the model emitted text
    in the wrong shape), the deserializer catches the
    ``pydantic.ValidationError`` and returns a sentinel
    ``JudgeVerdict(score=0.0, passed=False, reasoning="<deserialization
    failed>", unsupported_claims=[])`` rather than raising.

    Pitfall 6 rationale: structured-output failures are MEASUREMENTS,
    not retry triggers — Phase 9 metrics aggregate over the failure rate;
    raising would convert a per-call regression into a hard crash and
    distort the eval signal.

    The test patches ``adapters.real.judge._judge_via_anthropic_raw`` (the
    raw SDK helper under the ``CrossFamilyJudge`` Phase 2 D-04 wiring) to
    return a payload that won't deserialize. To exercise the Anthropic
    dispatch path under D-04 cross-family wiring, the bundle is built with
    ``llm_real_provider="openai"`` so the judge complement is the
    Anthropic adapter (generator=openai → judge=anthropic). Plan 06-06
    ships the helper + the sentinel fallback; this test asserts the
    sentinel verdict shape.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.types import JudgeVerdict
    from docintel_core.config import Settings
    from pydantic import SecretStr

    bundle = make_adapters(
        Settings(
            llm_provider="real",
            llm_real_provider="openai",
            anthropic_api_key=SecretStr("dummy-anthropic-key-for-test"),
            openai_api_key=SecretStr("dummy-openai-key-for-test"),
        )
    )

    # Patch the internal Anthropic raw SDK helper so no real API call is made.
    # Plan 06-06 lands `_judge_via_anthropic_raw` (the @retry-wrapped raw
    # structured-output helper); we mock its return-value shape to a payload
    # that fails JudgeVerdict deserialization. The outer `_judge_via_anthropic`
    # wrapper catches the ValidationError and returns the sentinel.
    def _bad_payload(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"invalid": "shape", "missing_all_four_fields": True}

    with patch(
        "docintel_core.adapters.real.judge._judge_via_anthropic_raw",
        side_effect=_bad_payload,
    ):
        verdict = bundle.judge.judge(
            prediction="anything", reference=["anything"], rubric=""
        )

    # The sentinel verdict per D-09 + Pitfall 6.
    assert isinstance(verdict, JudgeVerdict), (
        f"D-09 sentinel: result must still be a JudgeVerdict; got {type(verdict).__name__}"
    )
    assert verdict.score == 0.0, (
        f"D-09 sentinel: score must be 0.0 on deserialization failure; got {verdict.score!r}"
    )
    assert verdict.passed is False, (
        f"D-09 sentinel: passed must be False on deserialization failure; got {verdict.passed!r}"
    )
    assert verdict.reasoning == "<deserialization failed>", (
        f"D-09 sentinel: reasoning must be '<deserialization failed>'; "
        f"got {verdict.reasoning!r}"
    )
    assert verdict.unsupported_claims == [], (
        f"D-09 sentinel: unsupported_claims must be empty list; "
        f"got {verdict.unsupported_claims!r}"
    )
