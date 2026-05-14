"""Plan 05-04 — NullReranker + NullBM25Store (Phase 5 D-08 ablation seam).

Covers VALIDATION.md rows 05-01-03 and 05-01-04 — the ablation seam for Phase 11:

* test_null_reranker_preserves_order — NullReranker returns docs in input order
  with ``score = -float(rank)`` (preserves input order under descending sort).
* test_null_reranker_satisfies_protocol — NullReranker is structurally a Reranker
  (Protocol is @runtime_checkable; structural mismatch fails isinstance).
* test_null_reranker_empty_docs — NullReranker on an empty docs list returns
  ``[]`` without exception (edge case).
* test_null_bm25_empty — NullBM25Store.query always returns ``[]``; ``name`` is
  ``"null-bm25"``; ``last_vocab_size`` returns 0; ``commit`` returns the 64-zero
  sentinel; ``verify`` returns True.
* test_null_bm25_satisfies_protocol — NullBM25Store is structurally a BM25Store
  (must expose the full 6-method Protocol surface: name, add, commit, query,
  verify, last_vocab_size).

Plan 05-01 marked these xfail-strict; Plan 05-04 ships ``null_adapters.py`` and
removes those markers. The Protocol satisfaction tests are the structural
defense — if a method is ever removed from ``NullBM25Store``, the
``isinstance`` check fails immediately.

Analogs:
* ``tests/test_adapters.py`` ``test_stub_reranker_sorted`` /
  ``test_stub_reranker_deterministic`` (lines 68-89) — protocol-satisfaction
  pattern via isinstance().
* ``packages/docintel-core/src/docintel_core/adapters/stub/reranker.py`` —
  StubReranker's structural-typing pattern (no inheritance).
* 05-PATTERNS.md ``tests/test_null_adapters.py`` section + RESEARCH.md
  Pattern 3.
"""

from __future__ import annotations


def test_null_reranker_preserves_order() -> None:
    """D-08 — NullReranker returns docs in input order with score = -float(rank)."""
    from docintel_retrieve.null_adapters import NullReranker

    docs = ["alpha", "beta", "gamma"]
    out = NullReranker().rerank("query", docs)
    assert [d.doc_id for d in out] == ["0", "1", "2"]
    assert [d.text for d in out] == ["alpha", "beta", "gamma"]
    # Score is negated rank — sort by score descending preserves input order.
    assert [d.score for d in out] == [0.0, -1.0, -2.0]
    assert [d.original_rank for d in out] == [0, 1, 2]


def test_null_reranker_satisfies_protocol() -> None:
    """D-08 — NullReranker is structurally a Reranker."""
    from docintel_core.adapters.protocols import Reranker
    from docintel_retrieve.null_adapters import NullReranker

    assert isinstance(NullReranker(), Reranker)


def test_null_reranker_empty_docs() -> None:
    """D-08 edge case — NullReranker on empty docs returns [] without exception."""
    from docintel_retrieve.null_adapters import NullReranker

    assert NullReranker().rerank("query", []) == []


def test_null_bm25_empty() -> None:
    """D-08 — NullBM25Store.query always returns [] and full method surface returns stable sentinels."""
    from docintel_retrieve.null_adapters import NullBM25Store

    store = NullBM25Store()
    assert store.query("any query", k=100) == []
    assert store.name == "null-bm25"
    assert store.last_vocab_size() == 0
    assert store.commit() == "0" * 64
    assert store.verify() is True


def test_null_bm25_satisfies_protocol() -> None:
    """D-08 — NullBM25Store is structurally a BM25Store (full 6-method surface)."""
    from docintel_core.adapters.protocols import BM25Store
    from docintel_retrieve.null_adapters import NullBM25Store

    assert isinstance(NullBM25Store(), BM25Store)
