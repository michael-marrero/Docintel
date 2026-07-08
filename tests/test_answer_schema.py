"""Phase 7 Plan 01-03 tests for ANS-01 Answer Pydantic shape (D-01..D-05).

Covers VALIDATION.md rows for ANS-01 — the Phase 7 → Phase 9/13 public
contract for the Answer schema:

* test_answer_has_five_fields — the five D-01 fields are all accepted
  (text, citations, confidence, refused, prompt_version_hash).
* test_answer_frozen — ``ConfigDict(frozen=True)`` raises
  ``pydantic.ValidationError`` on post-construction mutation.
* test_answer_extra_forbid — ``ConfigDict(extra="forbid")`` raises
  on construction with unknown fields (defense against schema drift).
* test_confidence_literal — confidence="very_high" (not in
  Literal["high","medium","low"]) raises ValidationError (D-03).
* test_citations_required_when_not_refused — refused=False + citations=[]
  raises ValidationError from the ANS-03 model-validator (D-13).
* test_refusal_empty_citations_valid — refused=True + citations=[] +
  confidence="low" constructs without error (D-05).

Analogs:
* ``tests/test_generation_result_schema.py`` (full file, 92 lines) —
  Phase 6 D-17 ``GenerationResult`` analog; same Pydantic-frozen +
  extra=forbid test pattern; same ``_ok_payload()`` helper convention.
* ``tests/test_retrieved_chunk_schema.py`` (full file, 99 lines) —
  Phase 5 D-03 ``RetrievedChunk`` analog; same test structure.
* 07-PATTERNS.md §"tests/test_answer_schema.py" — payload helpers,
  refusal-variant payload, Literal-rejection test, model-validator test.
"""

from __future__ import annotations

import pytest


def _ok_citation_payload() -> dict:
    """Canonical ANS-02 7-field Citation payload — used across tests in this file."""
    return {
        "chunk_id": "AAPL-FY2024-Item-1A-007",
        "company": "Apple Inc.",
        "fiscal_year": 2024,
        "item_code": "Item 1A",
        "item_title": "Risk Factors",
        "text": "Apple identified supplier concentration as a key risk.",
        "char_span_in_section": (0, 55),
    }


def _ok_answer_payload() -> dict:
    """Canonical ANS-01 5-field Answer payload for a non-refusal answer.

    citations must be non-empty when refused=False (ANS-03 model-validator).
    Uses _ok_citation_payload() for the single-citation list.
    """
    return {
        "text": "Apple identified supplier concentration as a key risk.",
        "citations": [_ok_citation_payload()],
        "confidence": "high",
        "refused": False,
        "prompt_version_hash": "abcdef012345",
    }


def test_answer_has_five_fields() -> None:
    """ANS-01 + D-01 — the five D-01 fields are all accepted on construction.

    text, citations, confidence, refused, prompt_version_hash — the exact
    5 fields that Phase 9 metrics and Phase 13 UI consume from Answer.
    """
    from docintel_core.types import Answer, Citation

    payload = _ok_answer_payload()
    answer = Answer(**payload)
    assert answer.text == "Apple identified supplier concentration as a key risk."
    assert len(answer.citations) == 1
    assert isinstance(answer.citations[0], Citation)
    assert answer.confidence == "high"
    assert answer.refused is False
    assert answer.prompt_version_hash == "abcdef012345"


def test_answer_frozen() -> None:
    """D-02 — Pydantic frozen=True; downstream callers must not mutate.

    Phase 9 metrics aggregate over a list of Answers; Phase 13 renders
    citations from them. frozen=True prevents accidental mutation of a
    shared instance (defense against shared-list corruption — follows
    GenerationResult and RetrievedChunk precedent).
    """
    from docintel_core.types import Answer
    from pydantic import ValidationError

    answer = Answer(**_ok_answer_payload())
    with pytest.raises(ValidationError):
        answer.refused = True  # type: ignore[misc]


def test_answer_extra_forbid() -> None:
    """D-02 — extra='forbid' rejects unknown fields on construction.

    Defense against schema drift: a future plan that adds a debug field
    to Answer must update the model explicitly. Passing an unknown field
    at construction time raises pydantic.ValidationError.
    """
    from docintel_core.types import Answer
    from pydantic import ValidationError

    payload = _ok_answer_payload()
    payload["extra_field"] = "x"
    with pytest.raises(ValidationError):
        Answer(**payload)


def test_confidence_literal() -> None:
    """D-03 — confidence: Literal["high","medium","low"] rejects other values.

    "very_high" is not in the Literal set; Pydantic must raise
    ValidationError at construction time (not silently coerce).
    """
    from docintel_core.types import Answer
    from pydantic import ValidationError

    payload = _ok_answer_payload()
    payload["confidence"] = "very_high"
    with pytest.raises(ValidationError):
        Answer(**payload)


def test_citations_required_when_not_refused() -> None:
    """D-13 / ANS-03 — not refused => len(citations) >= 1.

    The model_validator(mode="after") fires after full field construction
    and raises ValueError (wrapped as ValidationError by Pydantic) when
    refused=False but citations=[] (empty list). This is the ANS-03
    structural invariant that every non-refusal Answer is anchored to
    at least one citation.
    """
    from docintel_core.types import Answer
    from pydantic import ValidationError

    payload = _ok_answer_payload()
    payload["citations"] = []  # violates ANS-03: not refused but empty citations
    with pytest.raises(ValidationError):
        Answer(**payload)


def test_refusal_empty_citations_valid() -> None:
    """D-05 — refused=True + citations=[] + confidence="low" is valid.

    On the refusal branch, citations=[] is correct (there are no grounded
    claims) and confidence="low" is mandatory. This test asserts that the
    model_validator does NOT fire on the refusal path, since the invariant
    is 'not refused => citations non-empty' (not 'always non-empty').
    """
    from docintel_core.types import Answer

    answer = Answer(
        text="I cannot answer this question from the retrieved 10-K excerpts.",
        citations=[],
        confidence="low",
        refused=True,
        prompt_version_hash="abcdef012345",
    )
    assert answer.refused is True
    assert answer.citations == []
    assert answer.confidence == "low"
