"""Plan 06-01 Wave 0 xfail scaffolds for GEN-04 dual-layer refusal path.

Covers VALIDATION.md row 06-06-* (GEN-04 + D-10 + D-11 + D-15) — the
Phase 6 refusal contract that the hero GIF's out-of-corpus demo + Phase 9
MET-03 (faithfulness rate) both consume:

* test_hard_zero_chunk_refusal — D-15 Step B: when ``retrieved_chunks``
  is ``[]``, the generator returns ``GenerationResult(text=
  REFUSAL_TEXT_SENTINEL, refused=True, completion=None,
  cited_chunk_ids=[], retrieved_chunks=[])`` WITHOUT calling the LLM
  (saves a call + cost).
* test_llm_driven_refusal — D-15 Step D + D-11: when retrieval returns
  plausibly-relevant chunks BUT the LLM emits ``REFUSAL_TEXT_SENTINEL``
  verbatim (the LLM correctly recognises the chunks don't answer the
  question), ``refused=True`` is set via the post-hoc
  ``response.text.startswith(REFUSAL_TEXT_SENTINEL)`` check. The LLM
  WAS called so ``completion is not None``.
* test_zero_chunks_warning — D-15 Step B + RESEARCH §Pattern 1 line 352:
  the hard-floor path emits exactly one
  ``generator_refused_zero_chunks`` structlog warning (visible-not-silent
  — Phase 9 MET-* and Phase 12 ``trace_id`` binding both source from
  this stream).

All three tests are xfail-strict-marked because ``Generator`` +
``REFUSAL_TEXT_SENTINEL`` do not yet exist at Wave 0. The in-function
imports raise ImportError → pytest counts this as the expected failure
under xfail(strict=True). Plan 06-04 ships the Generator's Step B + Step D
refusal logic + Plan 06-02 ships ``REFUSAL_TEXT_SENTINEL`` in
``docintel_core.types`` (per the D-11 + Pitfall 9 resolution: sentinel
lives in core so Phase 7 imports without depending on docintel-generate).

Analogs:
* ``tests/test_retriever_search.py:test_zero_candidates`` (lines 166-217)
  — CD-07 zero-candidate path + ``capture_logs`` warning assertion.
* ``tests/test_retriever_search.py:27 + 43 + 107-127`` — canonical
  ``structlog.testing.capture_logs`` usage in this codebase.
* 06-PATTERNS.md §"Tests scaffolds" line 849 (analog assignment).
"""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs


def _stub_retrieved_chunks() -> list[Any]:
    """Single representative chunk for the LLM-driven refusal test."""
    from docintel_core.types import RetrievedChunk

    return [
        RetrievedChunk(
            chunk_id="AAPL-FY2024-Item-1A-007",
            text="Apple identifies supplier concentration as a key risk.",
            score=0.9,
            ticker="AAPL",
            fiscal_year=2024,
            item_code="Item 1A",
            char_span_in_section=(100, 250),
        )
    ]


class _FakeRetriever:
    """Test double whose ``.search`` returns a pre-baked list of chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def search(self, query: str, k: int = 5) -> list[Any]:
        del query, k
        return list(self._chunks)


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 ships Step B hard-refusal")
def test_hard_zero_chunk_refusal() -> None:
    """D-15 Step B + D-11 — empty retrieval → hard refusal without LLM call.

    Retrieval returning ``[]`` skips the LLM entirely (saves a call + cost)
    and returns the canonical refusal sentinel. The Phase 6 D-11 sentinel
    lives in ``docintel_core.types`` (Pitfall 9 resolution — Phase 7's
    Answer wrapper consumes this contract without depending on the
    ``docintel-generate`` package).
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_core.types import REFUSAL_TEXT_SENTINEL
    from docintel_generate.generator import Generator

    bundle = make_adapters(Settings(llm_provider="stub"))
    retriever = _FakeRetriever([])  # empty retrieval → Step B
    g = Generator(bundle=bundle, retriever=retriever)
    r = g.generate("nonsense out-of-corpus query", k=5)

    assert r.refused is True, f"D-15 Step B: refused must be True; got {r.refused!r}"
    assert r.text == REFUSAL_TEXT_SENTINEL, (
        f"D-11: refusal text must equal REFUSAL_TEXT_SENTINEL; got {r.text!r}"
    )
    assert r.completion is None, (
        f"D-15 Step B: LLM must NOT be called on hard-refusal; got completion={r.completion!r}"
    )
    assert r.cited_chunk_ids == [], (
        f"D-15 Step B: no citations on hard-refusal; got {r.cited_chunk_ids!r}"
    )
    assert r.retrieved_chunks == [], (
        f"D-15 Step B: retrieved_chunks must be empty; got {r.retrieved_chunks!r}"
    )


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 ships Step D `.startswith(REFUSAL_TEXT_SENTINEL)`")
def test_llm_driven_refusal() -> None:
    """D-15 Step D + D-11 — LLM-driven refusal sets refused=True; completion is non-None.

    Retrieval returns ONE chunk (NOT empty, so Step B's hard-floor path is
    bypassed); the underlying LLM is mocked to emit ``REFUSAL_TEXT_SENTINEL``
    verbatim. The Step D post-hoc check ``response.text.startswith(
    REFUSAL_TEXT_SENTINEL)`` flips ``refused=True``; ``completion is not None``
    because the LLM was actually called; ``cited_chunk_ids == []`` because
    the sentinel string contains no bracket markers.

    This is the more impressive failure mode for the hero GIF — it says
    "the LLM is grounded, not just templating" (06-CONTEXT.md §specifics
    line 306).
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.types import CompletionResponse, Usage
    from docintel_core.config import Settings
    from docintel_core.types import REFUSAL_TEXT_SENTINEL
    from docintel_generate.generator import Generator

    base_bundle = make_adapters(Settings(llm_provider="stub"))

    class _FakeLLM:
        name = "fake-refuser"

        def complete(self, prompt: str, system: str | None = None) -> CompletionResponse:
            del prompt, system
            return CompletionResponse(
                text=REFUSAL_TEXT_SENTINEL,
                usage=Usage(prompt_tokens=10, completion_tokens=20),
                cost_usd=0.0,
                latency_ms=0.0,
                model="fake-refuser",
            )

    bundle = base_bundle.model_copy(update={"llm": _FakeLLM()})
    retriever = _FakeRetriever(_stub_retrieved_chunks())  # one chunk → bypass Step B
    g = Generator(bundle=bundle, retriever=retriever)
    r = g.generate("question with retrieved but unhelpful context", k=1)

    assert r.refused is True, f"D-15 Step D: refused must be True; got {r.refused!r}"
    assert r.completion is not None, (
        "D-15 Step D: LLM was called on the non-empty-retrieval path; "
        f"completion must be non-None; got {r.completion!r}"
    )
    assert r.cited_chunk_ids == [], (
        f"D-11: refusal sentinel has no bracket markers; "
        f"cited_chunk_ids must be empty; got {r.cited_chunk_ids!r}"
    )


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 emits generator_refused_zero_chunks structlog")
def test_zero_chunks_warning() -> None:
    """D-15 Step B + RESEARCH §Pattern 1 line 352 — generator_refused_zero_chunks structlog.

    Same setup as ``test_hard_zero_chunk_refusal`` but the assertion is on
    the visible-not-silent structlog stream: exactly one
    ``generator_refused_zero_chunks`` event fires on the hard-floor path.
    Phase 9 MET-03 (faithfulness rate) and Phase 12 ``trace_id``-binding
    both source from this stream.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_generate.generator import Generator

    bundle = make_adapters(Settings(llm_provider="stub"))
    retriever = _FakeRetriever([])
    g = Generator(bundle=bundle, retriever=retriever)

    with capture_logs() as records:
        g.generate("nonsense out-of-corpus query", k=5)

    events = [rec for rec in records if rec.get("event") == "generator_refused_zero_chunks"]
    assert len(events) == 1, (
        f"D-15 Step B: expected exactly one generator_refused_zero_chunks event; "
        f"got {len(events)} (all events={[r.get('event') for r in records]!r})"
    )
