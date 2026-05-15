"""Plan 06-01 Wave 0 xfail scaffold for D-16 generator_completed structlog telemetry.

Covers VALIDATION.md row 06-06-* (D-16) — the Phase 6 per-query telemetry
that Phase 9 MET-05 ($/query + p50/p95 latency), MET-03 (faithfulness),
and Phase 11 ablation reports source from:

* test_completed_fields — exactly one ``generator_completed`` event fires
  per ``generate()`` call AND that event carries all 15 named fields from
  the D-16 schema:
    1. query_tokens
    2. n_chunks_retrieved
    3. n_chunks_cited
    4. refused
    5. prompt_version_hash
    6. synthesis_hash
    7. refusal_hash
    8. judge_hash
    9. prompt_tokens
    10. completion_tokens
    11. cost_usd
    12. retrieval_ms
    13. generation_ms
    14. total_ms
    15. model

  The assertion is "each named field is present in the record dict", not
  the cardinal count (so a future plan that ADDS a sibling field doesn't
  go red here — it only goes red if a named field is REMOVED).

This test is xfail-strict-marked because ``Generator`` does not yet
emit the ``generator_completed`` line at Wave 0. The in-function
``from docintel_generate.generator import Generator`` raises ImportError
→ pytest counts this as the expected failure under xfail(strict=True).
Plan 06-04 ships ``Generator._emit_completed`` and this xfail flips to
passing.

Analogs:
* ``tests/test_retriever_search.py:test_telemetry_fields`` (lines 121-163)
  — the canonical ``capture_logs`` + named-field-presence pattern in this
  codebase (Phase 5 D-12 ``retriever_search_completed`` telemetry).
* ``tests/test_retriever_search.py:27 + 43 + 107-127 + 208`` — canonical
  ``structlog.testing.capture_logs`` usage.
* 06-RESEARCH.md §Pattern 1 lines 417-434 — the verbatim 15-field shape.
* 06-CONTEXT.md D-16 — the verbatim 15-field schema.
"""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs


def _stub_retrieved_chunks() -> list[Any]:
    """Single representative chunk so the LLM is exercised (not the Step B path)."""
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


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 emits generator_completed")
def test_completed_fields() -> None:
    """D-16 — generator_completed emits exactly once with all 15 named fields.

    Per RESEARCH §Pattern 1 lines 417-434 + CONTEXT.md D-16 — the line is:

        log.info(
            "generator_completed",
            query_tokens=q_tokens,
            n_chunks_retrieved=len(retrieved_chunks),
            n_chunks_cited=len(cited_chunk_ids),
            refused=refused,
            prompt_version_hash=PROMPT_VERSION_HASH,
            synthesis_hash=_SYNTHESIS_HASH,
            refusal_hash=_REFUSAL_HASH,
            judge_hash=_JUDGE_HASH,
            prompt_tokens=...,
            completion_tokens=...,
            cost_usd=...,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
            model=...,
        )

    Phase 9 MET-05 reads ``cost_usd`` + ``total_ms``; Phase 9 MET-03
    reads ``refused``; Phase 11 ablation reports diff fields across runs;
    Phase 12 binds ``trace_id`` automatically via ``contextvars`` once
    OBS-01 lands.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_generate.generator import Generator

    bundle = make_adapters(Settings(llm_provider="stub"))
    retriever = _FakeRetriever(_stub_retrieved_chunks())
    g = Generator(bundle=bundle, retriever=retriever)

    with capture_logs() as records:
        g.generate("revenue growth", k=1)

    completed = [rec for rec in records if rec.get("event") == "generator_completed"]
    assert len(completed) == 1, (
        f"D-16: telemetry must emit exactly one generator_completed line; "
        f"got {len(completed)} (all events={[r.get('event') for r in records]!r})"
    )
    rec = completed[0]
    required_fields = {
        "query_tokens",
        "n_chunks_retrieved",
        "n_chunks_cited",
        "refused",
        "prompt_version_hash",
        "synthesis_hash",
        "refusal_hash",
        "judge_hash",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "retrieval_ms",
        "generation_ms",
        "total_ms",
        "model",
    }
    missing = required_fields - set(rec.keys())
    assert not missing, (
        f"D-16: generator_completed missing fields {sorted(missing)!r}; "
        f"got record keys={sorted(rec.keys())!r}"
    )
