"""Plan 06-01 Wave 0 xfail scaffold for the hero question real-mode execution.

Covers VALIDATION.md "Manual-Only Verifications" row — the real-mode hero
question that the demo GIF (Phase 13 UI-03) and Phase 9 MET-* aggregate
metrics ultimately consume.

* test_generator_hero_real_mode — REAL-MODE end-to-end on the multi-hop
  comparative hero question ("Which of these companies grew R&D while
  margins shrank in 2023?"). Asserts:
    - ``refused is False`` (the LLM should find evidence in real-mode
      retrieval).
    - ``len(cited_chunk_ids) >= 2`` (multi-hop comparative MUST cite
      across at least two chunks — span check).
    - Tickers from cited chunks span >= 2 distinct values (multi-COMPANY
      coverage — the hero question is cross-company by construction).
    - ``r.completion.cost_usd < 0.20`` (CD-06 cost guard — a single hero
      call should be cheap).
    - ``r.completion.usage.prompt_tokens < 8000`` (CD-06 context-window
      budget — K=5 x ~500 BGE tokens + scaffolding < 8K).

This test carries BOTH the real-mode marker (OUTER, deselected by
``-m "not real"`` in CI) AND the xfail-strict marker (INNER,
preserved through Phase 6 per Phase 5 precedent on
``test_reranker_canary_real_mode``). The marker ORDERING is load-bearing:
pytest's marker-collection layer evaluates ``not real`` deselection
BEFORE applying the xfail, so the test is deselected from default CI
runs and only collected via ``-m real``.

Module-level ``pytestmark = pytest.mark.real`` is intentionally NOT
applied — that would gate the test behind the marker but doesn't add
any value here (there's only one test in this file); the function-level
pattern stays consistent with Phase 5 ``test_reranker_canary.py``.

The xfail marker is removed by Plan 06-07's xfail-removal sweep after
the first ``workflow_dispatch`` run against the phase/6-generation
branch records the rerank vs dense-only numbers and confirms the
acceptance criteria.

Analogs:
* ``tests/test_reranker_canary.py:test_reranker_canary_real_mode`` (lines
  350-406) — dual-mode marker pattern (function-level, not module-level);
  the docstring at lines 52-65 explains the rationale.
* 06-CONTEXT.md "Demo story (locked)" — hero question text.
* 06-CONTEXT.md CD-06 — context-budget + cost guards.
"""

from __future__ import annotations

import pytest


@pytest.mark.real
@pytest.mark.xfail(strict=True, reason="Wave 4 — Plan 06-07 promotes after workflow_dispatch run lands")
def test_generator_hero_real_mode() -> None:
    """Hero question — real-mode end-to-end + CD-06 cost + context-budget guards.

    Costs real API credits; gated by the real-mode marker (deselected on
    every PR's default ``-m "not real"`` run; collected only in the
    ``real-index-build`` workflow_dispatch job, mirroring Phase 4
    ``test_index_build_real.py`` and Phase 5
    ``test_reranker_canary_real_mode``).

    The hero question is multi-hop comparative across companies — the
    synthesis prompt has to handle it AND the single-doc factual case
    from Phase 8's ground-truth set under the same template (CD-01
    rationale). Phase 9 measurement will tell us if this holds.
    """
    from docintel_core.adapters.factory import make_generator
    from docintel_core.config import Settings

    g = make_generator(Settings(llm_provider="real", llm_real_provider="anthropic"))
    r = g.generate(
        "Which of these companies grew R&D while margins shrank in 2023?",
        k=5,
    )

    assert r.refused is False, (
        f"hero real-mode: should find evidence in real retrieval; "
        f"got refused={r.refused!r} text={r.text!r}"
    )
    assert len(r.cited_chunk_ids) >= 2, (
        f"hero real-mode: multi-hop comparative MUST cite >= 2 chunks; "
        f"got cited_chunk_ids={r.cited_chunk_ids!r}"
    )
    cited_tickers = {
        c.ticker for c in r.retrieved_chunks if c.chunk_id in r.cited_chunk_ids
    }
    assert len(cited_tickers) >= 2, (
        f"hero real-mode: multi-COMPANY coverage required (comparative across "
        f"companies); got cited_tickers={cited_tickers!r}"
    )
    assert r.completion is not None, (
        "hero real-mode: LLM was called; completion must be non-None"
    )
    assert r.completion.cost_usd < 0.20, (
        f"CD-06: single hero call must cost < $0.20; got cost_usd={r.completion.cost_usd!r}"
    )
    assert r.completion.usage.prompt_tokens < 8000, (
        f"CD-06: context-window budget — K=5 x ~500 + scaffolding < 8000; "
        f"got prompt_tokens={r.completion.usage.prompt_tokens!r}"
    )
