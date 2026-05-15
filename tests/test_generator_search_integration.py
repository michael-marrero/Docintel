"""Plan 06-01 Wave 0 xfail scaffold for D-14 + hero-question end-to-end stub.

Covers VALIDATION.md row 06-04-* (D-14 + hero) — the Phase 6 end-to-end
stub-mode integration of the FULL stack including the real ``Retriever``:

* test_hero_comparative_stub — ``make_generator(Settings(llm_provider=
  "stub"))`` returns a Generator whose ``generate(...)`` exercises the
  full pipeline (chunk_map eager-load + BM25 + dense + RRF + rerank in
  the Retriever; D-14 ``<context>``-block formatting + LLM call + Step D
  validation + Step E telemetry in the Generator). With the corpus-backed
  stub bundle, the hero comparative question must return at least one
  citation and a non-refused result.

The Phase 5 stub Retriever is corpus-backed (loads ``data/corpus/chunks/``
JSONL files); the stub LLM template emits ``[STUB ANSWER citing
[chunk_id]]`` markers verbatim. The combination produces a non-empty
``cited_chunk_ids`` list under stub mode, modulo the question landing on
at least one chunk via the BM25+dense fusion.

This test is xfail-strict-marked because ``make_generator`` does not yet
exist at Wave 0. The in-function
``from docintel_core.adapters.factory import make_generator`` raises
ImportError → pytest counts this as the expected failure under
xfail(strict=True). Plan 06-04 ships ``make_generator`` (composes
``make_adapters`` + ``make_retriever`` + ``Generator``) and this xfail
flips to passing.

Analogs:
* ``tests/test_retriever_search.py:test_retriever_returns_top_k`` (lines
  46-56) — factory-driven full-stack integration pattern.
* ``tests/test_make_retriever.py:test_chunk_map_eager_load`` (lines
  49-64) — corpus-backed assertion pattern.
* 06-CONTEXT.md "Demo story (locked)" — hero question text.
"""

from __future__ import annotations


def test_hero_comparative_stub() -> None:
    """D-14 + hero — end-to-end stub-mode generate() on the hero comparative question.

    The hero question (06-CONTEXT.md "Demo story (locked)"):
        "Which of these companies grew R&D while margins shrank in 2023?"

    Under stub mode:
    * Retriever loads the corpus, runs BM25+dense+RRF+rerank, returns
      up to K=5 ``RetrievedChunk`` instances.
    * Generator formats the D-14 ``<context>`` block, calls
      ``bundle.llm.complete(...)`` (stub adapter emits the templated
      ``[STUB ANSWER citing [chunk_id]]`` response), validates citations
      (Step D), and emits the ``generator_completed`` structlog
      (Step E).

    Assertions are minimal (existence + shape) — the goal is to prove
    the wiring works end-to-end, not to verify retrieval quality (that's
    Phase 5's canary in ``test_reranker_canary.py``; Phase 9 will measure
    Hit@K + faithfulness).
    """
    from docintel_core.adapters.factory import make_generator
    from docintel_core.config import Settings

    g = make_generator(Settings(llm_provider="stub"))
    r = g.generate(
        "Which of these companies grew R&D while margins shrank in 2023?",
        k=5,
    )
    assert r.refused is False, (
        f"D-14 hero: stub mode with corpus-backed chunks should not refuse; "
        f"got refused={r.refused!r} text={r.text!r}"
    )
    assert len(r.cited_chunk_ids) >= 1, (
        f"D-14 hero: at least one citation expected from stub answer template; "
        f"got cited_chunk_ids={r.cited_chunk_ids!r}"
    )
    assert r.completion is not None, (
        f"D-14 hero: LLM was called (non-empty retrieval → non-Step-B path); "
        f"completion must be non-None; got {r.completion!r}"
    )
    assert r.completion.model == "stub", (
        f"D-14 hero: stub-mode bundle.llm.complete must report model='stub'; "
        f"got model={r.completion.model!r}"
    )
    assert len(r.retrieved_chunks) <= 5, (
        f"D-14 hero: retrieved_chunks must be bounded by k=5; " f"got len={len(r.retrieved_chunks)}"
    )
