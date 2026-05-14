"""Plan 05-01 Wave 0 xfail scaffolds for Retriever.search (RET-02 + CD-07).

Covers VALIDATION.md rows 05-02-01..05-02-05 — the end-to-end stub-mode
contract for the Phase 5 single-seam Retriever.search():

* test_retriever_returns_top_k — top-K=5 returned after rerank of top-M=20
  (D-06 final answer shape).
* test_assertion_quotes_claude_md — the D-10 pre-rerank n_tokens<=500
  assertion message contains the verbatim CLAUDE.md hard-gate quote
  substrings (Pitfall 6 — failure mode self-documents at the seam).
* test_query_truncation_logs — D-11 query truncation at 64 tokens emits a
  ``retriever_query_truncated`` structlog warning (visible-not-silent).
* test_telemetry_fields — D-12 ``retriever_search_completed`` structlog
  line carries all per-stage timing + cardinality fields that Phase 9
  MET-05 + Phase 11 ablation reports source from.
* test_zero_candidates — CD-07 zero-candidate path returns ``[]`` with a
  ``retriever_search_zero_candidates`` structlog warning (Phase 6 GEN-04
  refusal path takes over from there).

All five tests are xfail-strict-marked because ``Retriever`` /
``make_retriever`` / ``docintel_retrieve.*`` do not yet exist at Wave 0.
The in-function imports raise ImportError → pytest counts this as the
expected failure under xfail(strict=True). Plan 05-05 ships retriever.py
and the factory and removes these xfail markers.

structlog log-capture pattern note (RESEARCH.md PATTERNS line 1099 — new
ground): tests use ``structlog.testing.capture_logs()`` as a context
manager (structlog 25.x canonical pattern). Phase 4's tests asserted on
the resulting MANIFEST.json — they do not have a log-capture analog.

Analogs:
* ``tests/test_index_stores.py`` end-to-end shape (construct → exercise → assert).
* ``tests/test_adapters.py`` factory-test pattern.
* 05-PATTERNS.md ``tests/test_retriever_search.py`` section.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (Retriever.search returns top-K=5 after rerank of top-M=20)")
def test_retriever_returns_top_k() -> None:
    """RET-02 — search(query, k=5) returns 5 RetrievedChunks (D-06; Plan 05-05)."""
    # In-function imports: nothing in docintel_retrieve exists at Wave 0.
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433
    from docintel_core.types import RetrievedChunk  # noqa: WPS433

    r = make_retriever(Settings(llm_provider="stub"))
    results = r.search("revenue growth in fiscal year", k=5)
    assert len(results) == 5
    for rc in results:
        assert isinstance(rc, RetrievedChunk)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (D-10 assertion message contains the verbatim CLAUDE.md quote substrings)")
def test_assertion_quotes_claude_md() -> None:
    """RET-02 — D-10 assertion message contains verbatim CLAUDE.md quote substrings (Pitfall 6, Plan 05-05)."""
    # The pre-rerank assertion fires when chunk.n_tokens > 500. The assertion
    # message MUST contain the verbatim CLAUDE.md hard-gate quote substrings so
    # the failure is self-documenting at the seam (Pitfall 6 — defense doubled).
    # Wave 1 plan ships the assertion + the _CLAUDE_MD_HARD_GATE module constant
    # in docintel_retrieve.retriever; this test asserts that an AssertionError
    # raised from .search() carries the verbatim substrings.
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    r = make_retriever(Settings(llm_provider="stub"))
    # Wave 2+ Plan 05-05 wires the monkeypatch / fixture that injects an
    # n_tokens>500 chunk into the top-20 rerank set. The xfail body here is
    # the scaffolded shape; Plan 05-05 replaces it with the real assertion
    # trigger.
    with pytest.raises(AssertionError) as exc_info:
        r.search("trigger the n_tokens>500 assertion", k=5)
    msg = str(exc_info.value)
    assert "BGE 512-token truncation FIRST" in msg, (
        "D-10 assertion message must contain the verbatim CLAUDE.md substring "
        "'BGE 512-token truncation FIRST' (Pitfall 6 — failure mode self-documents)"
    )
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in msg, (
        "D-10 assertion message must contain the verbatim CLAUDE.md substring "
        "'before suspecting hybrid retrieval, RRF, or chunk size' (Pitfall 6)"
    )


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (D-11 query truncation at 64 tokens with structlog warning)")
def test_query_truncation_logs() -> None:
    """RET-02 — D-11 query > 64 tokens triggers retriever_query_truncated structlog line (Plan 05-05)."""
    import structlog  # noqa: WPS433
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    r = make_retriever(Settings(llm_provider="stub"))
    long_query = " ".join(["token"] * 200)
    with structlog.testing.capture_logs() as records:
        r.search(long_query, k=5)
    events = [rec.get("event") for rec in records]
    assert "retriever_query_truncated" in events, (
        f"D-11 truncation must emit retriever_query_truncated; got events={events!r}"
    )
    truncation_records = [rec for rec in records if rec.get("event") == "retriever_query_truncated"]
    assert len(truncation_records) == 1
    rec = truncation_records[0]
    assert rec.get("truncated_to") == 64
    # original_tokens is the pre-truncation count — must be > 64 so the warning is meaningful.
    assert rec.get("original_tokens", 0) > 64


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (D-12 retriever_search_completed structlog line carries all per-stage fields)")
def test_telemetry_fields() -> None:
    """RET-02 — D-12 retriever_search_completed line contains all required fields (Plan 05-05)."""
    import structlog  # noqa: WPS433
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    r = make_retriever(Settings(llm_provider="stub"))
    with structlog.testing.capture_logs() as records:
        r.search("test query", k=5)
    completed = [rec for rec in records if rec.get("event") == "retriever_search_completed"]
    assert len(completed) == 1, (
        f"D-12 telemetry must emit exactly one retriever_search_completed line; got {len(completed)}"
    )
    rec = completed[0]
    # D-12 schema — every field that Phase 9 MET-05 + Phase 11 ablation reports source from.
    required_fields = {
        "query_tokens",
        "query_truncated",
        "bm25_candidates",
        "dense_candidates",
        "rrf_unique",
        "rerank_input",
        "results_returned",
        "bm25_ms",
        "dense_ms",
        "fuse_ms",
        "rerank_ms",
        "total_ms",
    }
    missing = required_fields - set(rec.keys())
    assert not missing, f"D-12 telemetry missing fields: {sorted(missing)!r}"


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (CD-07 zero-candidate path returns [] with structlog warning)")
def test_zero_candidates() -> None:
    """CD-07 — zero-candidate query path returns [] with structlog warning (Plan 05-05)."""
    # The zero-candidate path is exercised by constructing a Retriever with
    # NullBM25Store + an empty dense index (or by injecting a query that no
    # adapter retrieves anything for). Wave 1 plan refines the trigger; the
    # contract is: search() returns [] and emits retriever_search_zero_candidates.
    import structlog  # noqa: WPS433
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    r = make_retriever(Settings(llm_provider="stub"))
    with structlog.testing.capture_logs() as records:
        # Plan 05-05 wires the zero-candidate trigger; the scaffold uses an
        # implausible query as the placeholder mechanism.
        results = r.search("zzzzzzzzz-no-match-vocab-token-impossible-string-zzzzzzzzz", k=5)
    assert results == [], f"CD-07 zero-candidate path must return []; got {results!r}"
    events = [rec.get("event") for rec in records]
    assert "retriever_search_zero_candidates" in events, (
        f"CD-07 zero-candidate path must emit retriever_search_zero_candidates; got {events!r}"
    )
