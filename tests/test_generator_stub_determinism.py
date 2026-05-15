"""Plan 06-01 Wave 0 xfail scaffolds for GEN-03 stub-mode generator determinism.

Covers VALIDATION.md row 06-04-* (GEN-03 + D-13 + CD-07) — the Phase 6
end-to-end stub-mode contract:

* test_determinism — three back-to-back ``generate(query, k)`` calls with
  identical input produce identical ``text`` and ``cited_chunk_ids``
  (ADP-07 stub determinism extends through the generator layer).
* test_citation_subset — D-13 Step D validation: ``cited_chunk_ids`` is a
  subset of the ``retrieved_chunks`` set (no hallucinated IDs reach the
  return shape).
* test_hallucinated_ids_dropped — D-13 Step D + CD-07: when the
  underlying LLM emits a hallucinated ``[chunk_id]`` not in the retrieved
  set, the ID is dropped from ``cited_chunk_ids`` AND the response
  ``text`` is preserved unchanged (no sentence stripping — Phase 9
  MET-04 measures the failure rate). A structlog warning
  ``generator_hallucinated_chunk_id`` fires for the dropped ID.

All three tests are xfail-strict-marked because ``Generator`` does not
yet live in ``docintel_generate.generator`` at Wave 0. The in-function
``from docintel_generate.generator import Generator`` raises ImportError
→ pytest counts this as the expected failure under xfail(strict=True).
Plan 06-04 ships ``Generator`` (with citation-validation Step D + the
CD-07 structlog warning) and these xfails flip to passing.

Analogs:
* ``tests/test_retriever_search.py:test_retriever_returns_top_k`` (lines
  46-56) — factory-driven invocation pattern.
* ``tests/test_retriever_search.py:27 + 43 + 107-127`` — canonical
  ``structlog.testing.capture_logs`` usage in this codebase.
* ``tests/test_adapters.py:test_stub_all_deterministic`` (lines 228-258)
  — 100-call ADP-07 fuzz pattern, here narrowed to 3 calls because the
  test asserts identity not stress.
* 06-PATTERNS.md §"Tests scaffolds" line 848 (analog assignment).
"""

from __future__ import annotations

from typing import Any

from structlog.testing import capture_logs


def _stub_retrieved_chunks() -> list[Any]:
    """Single representative chunk for stub-mode end-to-end tests.

    The ``RetrievedChunk`` import lives inside the helper so Wave 0
    ImportError-on-missing-module flows up to the xfail-strict boundary
    cleanly (the test function imports ``RetrievedChunk`` via this
    helper rather than at module top).
    """
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
    """Test double whose ``.search(query, k)`` returns the helper output verbatim.

    Used to decouple ``Generator`` from the real ``Retriever`` so tests
    exercise the generation layer in isolation (no chunk_map eager load,
    no BM25/dense/RRF/rerank pipeline). The fake honors the
    Phase 5 D-02 contract: ``search(query, k) -> list[RetrievedChunk]``.
    """

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def search(self, query: str, k: int = 5) -> list[Any]:
        del query, k  # determinism: same chunks regardless of input
        return list(self._chunks)


def test_determinism() -> None:
    """GEN-03 + ADP-07 — three identical generate() calls produce identical output.

    Stub determinism extends through the generator layer: same ``query``
    + same retrieved chunks → identical ``text`` and ``cited_chunk_ids``.
    Three calls is sufficient to assert identity (not stress); the
    Phase 2 ADP-07 100-call fuzz exists at the adapter layer and is not
    re-tested here.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_generate.generator import Generator

    bundle = make_adapters(Settings(llm_provider="stub"))
    retriever = _FakeRetriever(_stub_retrieved_chunks())
    g = Generator(bundle=bundle, retriever=retriever)
    r1 = g.generate("revenue growth", k=5)
    r2 = g.generate("revenue growth", k=5)
    r3 = g.generate("revenue growth", k=5)
    assert r1.text == r2.text == r3.text, (
        f"GEN-03: identical input must produce identical text; "
        f"got {r1.text!r} / {r2.text!r} / {r3.text!r}"
    )
    assert r1.cited_chunk_ids == r2.cited_chunk_ids == r3.cited_chunk_ids, (
        f"GEN-03: identical input must produce identical citations; "
        f"got {r1.cited_chunk_ids!r} / {r2.cited_chunk_ids!r} / {r3.cited_chunk_ids!r}"
    )


def test_citation_subset() -> None:
    """GEN-03 + D-13 Step D — cited_chunk_ids is a subset of retrieved set.

    D-13 step 4 validates every cited chunk_id against
    ``{c.chunk_id for c in retrieved_chunks}``. With a single retrieved
    chunk in the helper, every cited_chunk_id (if any) must be
    ``"AAPL-FY2024-Item-1A-007"``.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_generate.generator import Generator

    bundle = make_adapters(Settings(llm_provider="stub"))
    retriever = _FakeRetriever(_stub_retrieved_chunks())
    g = Generator(bundle=bundle, retriever=retriever)
    result = g.generate("revenue growth", k=1)
    retrieved_ids = {"AAPL-FY2024-Item-1A-007"}
    assert set(result.cited_chunk_ids).issubset(retrieved_ids), (
        f"D-13 Step D: cited_chunk_ids must be subset of retrieved set; "
        f"got cited={result.cited_chunk_ids!r}, retrieved={retrieved_ids!r}"
    )


def test_hallucinated_ids_dropped() -> None:
    """D-13 Step D + CD-07 — hallucinated chunk_ids dropped from cited list; text preserved.

    Builds a fake LLM whose ``.complete(...)`` returns a response
    referencing BOTH a real chunk_id (``AAPL-FY2024-Item-1A-007``, in the
    retrieved set) and a hallucinated one (``NVDA-FY2024-Item-7-999``,
    not in the retrieved set). After D-13 Step 4 runs:

    * The hallucinated ID is dropped from ``cited_chunk_ids``.
    * The response ``text`` is UNCHANGED (no sentence stripping — Phase 9
      MET-04 measures citation accuracy as a fraction; we don't paper
      over the failure).
    * A structlog warning ``generator_hallucinated_chunk_id`` fires.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.types import CompletionResponse, TokenUsage
    from docintel_core.config import Settings
    from docintel_generate.generator import Generator

    base_bundle = make_adapters(Settings(llm_provider="stub"))

    # Fake LLM emits a real + hallucinated chunk_id pair.
    class _FakeLLM:
        name = "fake-hallucination"

        def complete(self, prompt: str, system: str | None = None) -> CompletionResponse:
            del prompt, system
            return CompletionResponse(
                text=(
                    "Apple risk [AAPL-FY2024-Item-1A-007] and "
                    "[NVDA-FY2024-Item-7-999]."
                ),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10),
                cost_usd=0.0,
                latency_ms=0.0,
                model="fake-hallucination",
            )

    bundle = base_bundle.model_copy(update={"llm": _FakeLLM()})
    retriever = _FakeRetriever(_stub_retrieved_chunks())
    g = Generator(bundle=bundle, retriever=retriever)

    with capture_logs() as records:
        result = g.generate("apple risk", k=1)

    assert "AAPL-FY2024-Item-1A-007" in result.cited_chunk_ids, (
        f"D-13 Step D: real chunk_id must survive validation; got {result.cited_chunk_ids!r}"
    )
    assert "NVDA-FY2024-Item-7-999" not in result.cited_chunk_ids, (
        f"D-13 Step D: hallucinated chunk_id must be dropped; got {result.cited_chunk_ids!r}"
    )
    # Anti-pattern guard — text must NOT be modified (no sentence stripping per D-13).
    assert "[NVDA-FY2024-Item-7-999]" in result.text, (
        f"D-13 anti-pattern: hallucinated brackets must be preserved in text; "
        f"got text={result.text!r}"
    )
    # CD-07 structlog warning — exactly one generator_hallucinated_chunk_id event.
    events = [rec for rec in records if rec.get("event") == "generator_hallucinated_chunk_id"]
    assert len(events) >= 1, (
        f"CD-07: expected >= 1 generator_hallucinated_chunk_id event; "
        f"got events={[r.get('event') for r in records]!r}"
    )
