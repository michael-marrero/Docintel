"""Plan 05-01 Wave 0 xfail scaffolds for NullReranker + NullBM25Store (D-08).

Covers VALIDATION.md rows 05-01-03 and 05-01-04 — the ablation seam for Phase 11:

* test_null_reranker_preserves_order — NullReranker returns docs in input order
  with ``score = -float(rank)`` (preserves input order under descending sort).
* test_null_reranker_satisfies_protocol — NullReranker is structurally a Reranker
  (Protocol is @runtime_checkable; structural mismatch fails isinstance).
* test_null_bm25_empty — NullBM25Store.query always returns ``[]``; ``name`` is
  ``"null-bm25"``; ``last_vocab_size`` returns 0.
* test_null_bm25_satisfies_protocol — NullBM25Store is structurally a BM25Store
  (must expose the full 6-method Protocol surface: name, add, commit, query,
  verify, last_vocab_size).

All four tests are xfail-strict-marked because ``docintel_retrieve.null_adapters``
does not yet exist at Wave 0. The in-function import raises ImportError →
pytest counts this as the expected failure under xfail(strict=True). Plan 05-04
ships null_adapters.py and removes these xfail markers.

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

import pytest


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-04 (docintel_retrieve.null_adapters.NullReranker)")
def test_null_reranker_preserves_order() -> None:
    """D-08 — NullReranker returns docs in input order with score = -float(rank) (Plan 05-04)."""
    # In-function import: docintel_retrieve.null_adapters does not exist at Wave 0.
    from docintel_retrieve.null_adapters import NullReranker  # noqa: WPS433 — intentional

    docs = ["alpha", "beta", "gamma"]
    out = NullReranker().rerank("query", docs)
    assert [d.doc_id for d in out] == ["0", "1", "2"]
    assert [d.text for d in out] == ["alpha", "beta", "gamma"]
    # Score is negated rank — sort by score descending preserves input order.
    assert [d.score for d in out] == [0.0, -1.0, -2.0]


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-04 (docintel_retrieve.null_adapters.NullReranker)")
def test_null_reranker_satisfies_protocol() -> None:
    """D-08 — NullReranker is structurally a Reranker (Plan 05-04)."""
    from docintel_core.adapters.protocols import Reranker  # noqa: WPS433
    from docintel_retrieve.null_adapters import NullReranker  # noqa: WPS433

    assert isinstance(NullReranker(), Reranker)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-04 (docintel_retrieve.null_adapters.NullBM25Store)")
def test_null_bm25_empty() -> None:
    """D-08 — NullBM25Store.query always returns [] (Plan 05-04)."""
    from docintel_retrieve.null_adapters import NullBM25Store  # noqa: WPS433

    store = NullBM25Store()
    assert store.query("any query", k=100) == []
    assert store.name == "null-bm25"
    assert store.last_vocab_size() == 0


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-04 (docintel_retrieve.null_adapters.NullBM25Store)")
def test_null_bm25_satisfies_protocol() -> None:
    """D-08 — NullBM25Store is structurally a BM25Store (full 6-method surface; Plan 05-04)."""
    from docintel_core.adapters.protocols import BM25Store  # noqa: WPS433
    from docintel_retrieve.null_adapters import NullBM25Store  # noqa: WPS433

    assert isinstance(NullBM25Store(), BM25Store)
