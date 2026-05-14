"""Plan 05-05 end-to-end stub-mode tests for Retriever.search (RET-02 + CD-07).

Promoted from Wave 0 xfail scaffold (Plan 05-01). Plan 05-05 ships
``docintel_retrieve.retriever.Retriever`` + the ``make_retriever`` factory and
this file flips from five xfailed → five passed.

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
  ``retriever_search_zero_candidates`` structlog warning. Concrete-induction
  pattern: tmp_path-rooted Settings (corpus + index absent) + NullBM25Store +
  NumpyDenseStore on the empty index. The MANIFEST.json absence skips the
  cardinality check in ``_load_chunk_map``; warm-up failures are swallowed
  by the try/except guard in ``Retriever.__init__``.

structlog log-capture pattern: ``structlog.testing.capture_logs()`` as a
context manager (structlog 25.x canonical). RESEARCH.md PATTERNS line 1099 —
Phase 4 tests do not have a log-capture analog; this is new ground for
Phase 5.

Analogs:
* ``tests/test_index_stores.py`` end-to-end shape (construct → exercise → assert).
* ``tests/test_adapters.py`` factory-test pattern.
* 05-PATTERNS.md ``tests/test_retriever_search.py`` section.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs


def test_retriever_returns_top_k() -> None:
    """RET-02 — search(query, k=5) returns 5 RetrievedChunks (D-06)."""
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings
    from docintel_core.types import RetrievedChunk

    r = make_retriever(Settings(llm_provider="stub"))
    results = r.search("revenue growth in fiscal year", k=5)
    assert len(results) == 5
    for rc in results:
        assert isinstance(rc, RetrievedChunk)


def test_assertion_quotes_claude_md() -> None:
    """RET-02 — D-10 assertion message contains verbatim CLAUDE.md substrings (Pitfall 6).

    Construct a stub-mode Retriever, mutate one chunk in ``_chunk_map`` to
    have ``n_tokens=501`` so the pre-rerank assertion fires when that chunk
    is pulled into the top-20 RRF set. ``Chunk`` is non-frozen so the
    ``__dict__`` write is valid Pydantic v2 behaviour.

    The query is chosen so that the mutated chunk is reliably pulled into
    the top-20 fused set: we pick the first chunk in ``_chunk_map`` (sorted
    JSONL traversal — deterministic across machines) and embed its own
    leading tokens into the query. Stub BM25 + stub dense both score
    chunks by token overlap, so a query made of the chunk's own tokens
    guarantees the chunk lands in the top-N of at least one retriever.
    """
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings

    r = make_retriever(Settings(llm_provider="stub"))
    # Pick a chunk; sorted-JSONL traversal makes this deterministic.
    target_id = next(iter(r._chunk_map))  # noqa: SLF001 — intentional test-only access
    target_chunk = r._chunk_map[target_id]  # noqa: SLF001
    # Build a query from the chunk's own text — guarantees lexical overlap.
    chunk_tokens = target_chunk.text.lower().split()[:20]
    query = " ".join(chunk_tokens)
    # Mutate n_tokens to trigger D-10. Chunk is not frozen.
    target_chunk.__dict__["n_tokens"] = 501

    with pytest.raises(AssertionError) as exc_info:
        r.search(query, k=5)
    msg = str(exc_info.value)
    assert "BGE 512-token truncation FIRST" in msg, (
        "D-10 assertion message must contain the verbatim CLAUDE.md substring "
        "'BGE 512-token truncation FIRST' (Pitfall 6 — failure mode self-documents)"
    )
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in msg, (
        "D-10 assertion message must contain the verbatim CLAUDE.md substring "
        "'before suspecting hybrid retrieval, RRF, or chunk size' (Pitfall 6)"
    )


def test_query_truncation_logs() -> None:
    """RET-02 — D-11 query > 64 tokens triggers retriever_query_truncated structlog line."""
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings

    r = make_retriever(Settings(llm_provider="stub"))
    long_query = " ".join(["token"] * 200)
    with capture_logs() as records:
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


def test_telemetry_fields() -> None:
    """RET-02 — D-12 retriever_search_completed line contains all required fields."""
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings

    r = make_retriever(Settings(llm_provider="stub"))
    with capture_logs() as records:
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
    # Type sanity on a few fields — ms are non-negative floats; counts are non-negative ints.
    for ms_field in ("bm25_ms", "dense_ms", "fuse_ms", "rerank_ms", "total_ms"):
        assert isinstance(rec[ms_field], (int, float))
        assert rec[ms_field] >= 0.0
    for count_field in ("bm25_candidates", "dense_candidates", "rrf_unique", "rerank_input", "results_returned"):
        assert isinstance(rec[count_field], int)
        assert rec[count_field] >= 0


def test_zero_candidates(tmp_path: Path) -> None:
    """CD-07 — zero-fusion path returns [] with retriever_search_zero_candidates warning.

    Concrete-induction setup (no executor discovery required):

    * ``tmp_path``-rooted Settings — ``data_dir`` and ``index_dir`` are
      empty. ``data/corpus/chunks/`` is absent → ``_load_chunk_map`` rglob
      finds zero JSONLs → chunk_map = {}.
    * ``data/indices/MANIFEST.json`` is absent → the cardinality check in
      ``_load_chunk_map`` is skipped (the optional-manifest branch).
    * ``NullBM25Store.query(...)`` returns ``[]`` for any input (Plan 05-04
      D-08 contract enforced by ``tests/test_null_adapters.py::test_null_bm25_empty``).
    * ``NumpyDenseStore.query(...)`` on an empty / absent index returns
      ``[]`` (Phase 4 contract — verified via ``tests/test_index_stores.py``).
    * Warm-up calls in ``Retriever.__init__`` are wrapped in
      ``try/except Exception`` so empty-store warm-up does NOT prevent
      construction.

    The CD-07 zero-candidate guard in ``Retriever.search`` Step C runs::

        if not fused: log.warning("retriever_search_zero_candidates", ...); return []

    This is the load-bearing path the test asserts.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.real.numpy_dense import NumpyDenseStore
    from docintel_core.adapters.types import IndexStoreBundle
    from docintel_core.config import Settings
    from docintel_retrieve.null_adapters import NullBM25Store
    from docintel_retrieve.retriever import Retriever

    # tmp_path-rooted Settings — corpus tree empty, MANIFEST.json absent.
    cfg = Settings(
        llm_provider="stub",
        data_dir=str(tmp_path),
        index_dir=str(tmp_path / "data" / "indices"),
    )
    bundle = make_adapters(cfg)
    stores = IndexStoreBundle(bm25=NullBM25Store(), dense=NumpyDenseStore(cfg))
    # Construct directly — NOT via make_retriever — so we control both stores explicitly.
    r = Retriever(bundle=bundle, stores=stores, cfg=cfg)

    with capture_logs() as records:
        result = r.search("any query", k=5)

    # CD-07 — empty list returned, zero-candidate warning emitted.
    assert result == [], f"CD-07 expected empty list, got {result!r}"
    zero_events = [rec for rec in records if rec.get("event") == "retriever_search_zero_candidates"]
    assert len(zero_events) == 1, (
        f"CD-07 expected exactly one retriever_search_zero_candidates event, "
        f"got {len(zero_events)}"
    )
