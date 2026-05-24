"""Phase 7 Plan 01-03 tests for ANS-02, ANS-03, D-05, D-13, D-15, D-16.

Covers VALIDATION.md rows for from_generation_result — the Phase 7 conversion
classmethod that wraps GenerationResult into a citation-grade Answer:

* test_from_generation_result — non-refusal GenerationResult → Answer with
  correct Citation (company="Apple Inc.", item_title="Risk Factors",
  fiscal_year=2024) via injected fixture maps (D-16 Focus Q4 Option 2).
* test_refusal_path — refused=True GenerationResult → Answer(refused=True,
  citations=[], confidence="low") (D-05, ANS-03 refusal branch).
* test_refused_confidence_low — D-05: confidence=="low" on refused=True
  path even if the refusal text somehow contains a marker; parse_confidence
  is NOT called on the refusal branch (Pitfall 1).
* test_confidence_marker_stripped — Pitfall 6: "[confidence:" not in
  answer.text after from_generation_result (marker stripped from Answer.text).
* test_ans03_invariant_empty_cited_ids — cited_chunk_ids=[] + refused=False
  → ValidationError from the model-validator (D-13 / ANS-03 invariant).

Analogs:
* ``tests/test_generator_stub_determinism.py`` — GenerationResult
  fixture-construction patterns (_ok_gr_non_refusal/_ok_gr_refusal style).
* ``tests/test_generation_result_schema.py`` — _ok_payload() + in-function
  import conventions.
* 07-PATTERNS.md §"tests/test_from_generation_result.py" — fixture maps,
  refusal-path test, marker-stripped test, ANS-03 invariant test.
"""

from __future__ import annotations

from typing import Any

import pytest


# Small fixture maps injected via the optional keyword args of
# Answer.from_generation_result (D-16 Focus Q4 Option 2 — avoids filesystem
# coupling in test context; tests inject a small dict rather than reading CSV).
TICKER_MAP: dict[str, str] = {"AAPL": "Apple Inc."}
ITEM_MAP: dict[str, str] = {"Item 1A": "Risk Factors"}


def _ok_gr_non_refusal() -> Any:
    """Non-refusal GenerationResult fixture for from_generation_result tests.

    text includes a trailing [confidence: high] marker (stub determinism:
    real LLM emits this per the edited SYNTHESIS_PROMPT) and an inline
    [chunk_id] citation matching a RetrievedChunk in retrieved_chunks.
    """
    from docintel_core.types import GenerationResult, RetrievedChunk

    rc = RetrievedChunk(
        chunk_id="AAPL-FY2024-Item-1A-007",
        text="Apple disclosed supplier concentration as a key risk factor.",
        score=0.9,
        ticker="AAPL",
        fiscal_year=2024,
        item_code="Item 1A",
        char_span_in_section=(0, 61),
    )
    return GenerationResult(
        text=(
            "Apple disclosed supplier concentration as a key risk "
            "[AAPL-FY2024-Item-1A-007]\n[confidence: high]"
        ),
        cited_chunk_ids=["AAPL-FY2024-Item-1A-007"],
        refused=False,
        retrieved_chunks=[rc],
        completion=None,
        prompt_version_hash="abcdef012345",
    )


def _ok_gr_refusal() -> Any:
    """Refusal GenerationResult fixture — refused=True, no retrieved chunks."""
    from docintel_core.types import GenerationResult, REFUSAL_TEXT_SENTINEL

    return GenerationResult(
        text=REFUSAL_TEXT_SENTINEL,
        cited_chunk_ids=[],
        refused=True,
        retrieved_chunks=[],
        completion=None,
        prompt_version_hash="abcdef012345",
    )


def test_from_generation_result() -> None:
    """ANS-02 + ANS-03 + D-15 + D-16 — non-refusal path builds Answer with one Citation.

    Injects fixture maps (D-16 Focus Q4 Option 2) to avoid filesystem coupling.
    Asserts company="Apple Inc." (from TICKER_MAP), item_title="Risk Factors"
    (from ITEM_MAP), fiscal_year=2024 (from RetrievedChunk.fiscal_year).
    """
    from docintel_core.types import Answer

    gr = _ok_gr_non_refusal()
    answer = Answer.from_generation_result(
        gr,
        ticker_name_map=TICKER_MAP,
        item_code_title_map=ITEM_MAP,
    )
    assert answer.refused is False
    assert len(answer.citations) == 1
    citation = answer.citations[0]
    assert citation.company == "Apple Inc."
    assert citation.item_title == "Risk Factors"
    assert citation.fiscal_year == 2024


def test_refusal_path() -> None:
    """D-05 + ANS-03 — refused=True GenerationResult → Answer(refused=True, citations=[], confidence="low").

    On the refusal branch, from_generation_result must return an Answer with
    refused=True, citations=[], and confidence="low" unconditionally (D-05).
    """
    from docintel_core.types import Answer

    gr = _ok_gr_refusal()
    answer = Answer.from_generation_result(
        gr,
        ticker_name_map=TICKER_MAP,
        item_code_title_map=ITEM_MAP,
    )
    assert answer.refused is True
    assert answer.citations == []
    assert answer.confidence == "low"


def test_refused_confidence_low() -> None:
    """D-05 + Pitfall 1 — confidence="low" on refused=True even if text contains a marker.

    parse_confidence is NOT called on the refusal branch. The confidence is set
    unconditionally to "low" regardless of what text contains. This guards
    against Pitfall 1: a real LLM might append [confidence: low] to the
    refusal sentinel — that text must NOT flow through parse_confidence.
    """
    from docintel_core.types import Answer, GenerationResult, REFUSAL_TEXT_SENTINEL

    # Construct a refusal-ish GenerationResult whose text (hypothetically)
    # contains a confidence marker — the refusal branch must still yield "low".
    gr = GenerationResult(
        text=REFUSAL_TEXT_SENTINEL + "\n[confidence: medium]",
        cited_chunk_ids=[],
        refused=True,
        retrieved_chunks=[],
        completion=None,
        prompt_version_hash="abcdef012345",
    )
    answer = Answer.from_generation_result(
        gr,
        ticker_name_map=TICKER_MAP,
        item_code_title_map=ITEM_MAP,
    )
    assert answer.confidence == "low", (
        "D-05: refused=True must always produce confidence='low', "
        f"even when text contains a marker; got confidence={answer.confidence!r}"
    )


def test_confidence_marker_stripped() -> None:
    """Pitfall 6 — '[confidence:' not in answer.text after from_generation_result.

    The raw confidence marker appended to the synthesis text must be stripped
    by from_generation_result so Phase 13 UI never renders the bracket literal.
    """
    from docintel_core.types import Answer

    gr = _ok_gr_non_refusal()
    answer = Answer.from_generation_result(
        gr,
        ticker_name_map=TICKER_MAP,
        item_code_title_map=ITEM_MAP,
    )
    assert "[confidence:" not in answer.text, (
        f"Pitfall 6: confidence marker must be stripped from Answer.text; "
        f"got text={answer.text!r}"
    )


def test_ans03_invariant_empty_cited_ids() -> None:
    """D-13 / ANS-03 — cited_chunk_ids=[] + refused=False → ValidationError.

    Simulates the case where hallucination-drop clears all cited IDs
    (Phase 6 D-13 Step D). The ANS-03 model-validator must fire and raise
    ValidationError (via ValueError internally) because refused=False with
    no citations violates the structural invariant.
    """
    from docintel_core.types import Answer, GenerationResult, RetrievedChunk
    from pydantic import ValidationError

    rc = RetrievedChunk(
        chunk_id="AAPL-FY2024-Item-1A-007",
        text="Some text.",
        score=0.9,
        ticker="AAPL",
        fiscal_year=2024,
        item_code="Item 1A",
        char_span_in_section=(0, 10),
    )
    gr = GenerationResult(
        # Non-refusal but no cited_chunk_ids (all hallucinated, all dropped)
        text="Some synthesis text.\n[confidence: medium]",
        cited_chunk_ids=[],
        refused=False,
        retrieved_chunks=[rc],
        completion=None,
        prompt_version_hash="abcdef012345",
    )
    with pytest.raises(ValidationError):
        Answer.from_generation_result(
            gr,
            ticker_name_map=TICKER_MAP,
            item_code_title_map=ITEM_MAP,
        )


def test_load_ticker_name_map_reads_committed_csv() -> None:
    """D-07/D-16 regression — the module-level loader resolves the committed CSV.

    Guards against the repo-root path off-by-one (parents[N]): every other test
    injects ``ticker_name_map=`` and never exercises the on-disk fallback, so a
    wrong ``parents[]`` index raises FileNotFoundError ONLY in production. This
    test calls the loader directly so that failure surfaces in CI.
    """
    from docintel_core.types import _load_ticker_name_map

    _load_ticker_name_map.cache_clear()
    result = _load_ticker_name_map()
    assert result, "ticker→name map loaded from companies.snapshot.csv must be non-empty"
    assert result["AAPL"] == "Apple Inc."


def test_from_generation_result_no_injected_maps_uses_disk() -> None:
    """D-07/D-16 regression — from_generation_result works without injected maps.

    Exercises the real production seam Phase 13 calls: no ticker_name_map and no
    item_code_title_map are passed, so company resolves from the committed CSV
    and item_title from the module-level _ITEM_CODE_TITLE_MAP. This is the path
    the off-by-one path bug broke (and that the all-injecting tests masked).
    Also asserts the no-marker default: text without a [confidence:] marker
    yields confidence="medium" (WR-03 fallback coverage).
    """
    from docintel_core.types import Answer, GenerationResult, RetrievedChunk

    rc = RetrievedChunk(
        chunk_id="AAPL-FY2024-Item-1A-007",
        text="Apple disclosed supplier concentration as a key risk factor.",
        score=0.9,
        ticker="AAPL",
        fiscal_year=2024,
        item_code="Item 1A",
        char_span_in_section=(0, 61),
    )
    gr = GenerationResult(
        # No trailing [confidence: ...] marker → parse_confidence returns None →
        # from_generation_result defaults confidence to "medium".
        text="Apple disclosed supplier concentration [AAPL-FY2024-Item-1A-007]",
        cited_chunk_ids=["AAPL-FY2024-Item-1A-007"],
        refused=False,
        retrieved_chunks=[rc],
        completion=None,
        prompt_version_hash="abcdef012345",
    )
    answer = Answer.from_generation_result(gr)  # no injected maps — reads disk
    assert len(answer.citations) == 1
    assert answer.citations[0].company == "Apple Inc."
    assert answer.citations[0].item_title == "Risk Factors"
    assert answer.confidence == "medium"
