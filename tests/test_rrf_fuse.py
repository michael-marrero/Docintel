"""Plan 05-01 Wave 0 xfail scaffolds for _rrf_fuse (RET-01, D-07).

Covers VALIDATION.md rows 05-01-01 and 05-01-02:

* test_rrf_fuse_known_score — synthetic 1-chunk hand-computed RRF score asserts
  the 1-based Cormack 2009 formula ``1/(k + rank)``.
* test_rrf_skip_missing — chunk in only one ranker contributes from that
  ranker only; missing-side contribution is skipped (NOT a zero-rank penalty).
* test_rrf_one_based_ranks — input ranks are 0-based (industry convention from
  DenseStore.query / BM25Store.query); _rrf_fuse converts to 1-based in the
  formula denominator (Pitfall 5).
* test_rrf_k_constant — RRF_K is pinned at 60 (D-07; Cormack 2009 default).

All four tests are xfail-strict-marked because ``docintel_retrieve.fuse`` does
not yet exist at Wave 0. The in-function ``from docintel_retrieve.fuse import
RRF_K, _rrf_fuse`` raises ImportError → pytest counts this as the expected
failure under xfail(strict=True). Plan 05-03 ships fuse.py and removes these
xfail markers (the test bodies become real pass-when-correct assertions).

Analog: ``tests/test_index_stores.py`` end-to-end unit-test shape; pure-function
contract pattern from RESEARCH.md §1 + 05-PATTERNS.md ``tests/test_rrf_fuse.py``
section.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-03 (docintel_retrieve.fuse._rrf_fuse)")
def test_rrf_fuse_known_score() -> None:
    """RET-01 — synthetic case with hand-computed RRF score (Plan 05-03)."""
    # In-function import: docintel_retrieve.fuse does not exist at Wave 0.
    # ImportError here is the "real" xfail signal; Plan 05-03 removes this xfail.
    from docintel_retrieve.fuse import _rrf_fuse  # noqa: WPS433 — intentional in-function import

    # Two rankers, one chunk in both at rank 0 (0-based input → 1-based in formula).
    # Expected RRF = 1/(60+1) + 1/(60+1) = 2/61.
    bm25 = [("c1", 0, 12.3)]
    dense = [("c1", 0, 0.95)]
    result = _rrf_fuse(bm25, dense)
    assert len(result) == 1
    assert result[0][0] == "c1"
    assert result[0][1] == pytest.approx(2.0 / 61.0)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-03 (docintel_retrieve.fuse._rrf_fuse)")
def test_rrf_skip_missing() -> None:
    """RET-01 — chunk in only one ranker contributes from that ranker only (Plan 05-03)."""
    from docintel_retrieve.fuse import _rrf_fuse  # noqa: WPS433 — intentional in-function import

    # c1 in BM25 only at rank 0; c2 in dense only at rank 0.
    # Each contributes 1/(60+1) = 1/61 from its single ranker; both equal.
    bm25 = [("c1", 0, 12.3)]
    dense = [("c2", 0, 0.95)]
    result = _rrf_fuse(bm25, dense)
    assert len(result) == 2
    chunk_ids = {row[0] for row in result}
    assert chunk_ids == {"c1", "c2"}
    # Both chunks score 1/61; no missing-side penalty.
    for _chunk_id, score in result:
        assert score == pytest.approx(1.0 / 61.0)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-03 (docintel_retrieve.fuse._rrf_fuse)")
def test_rrf_one_based_ranks() -> None:
    """RET-01 — 0-based input ranks → 1-based in the RRF denominator (Pitfall 5, Plan 05-03)."""
    from docintel_retrieve.fuse import _rrf_fuse  # noqa: WPS433 — intentional in-function import

    # c1 at rank 0 in BM25 only. With 1-based conversion: RRF = 1/(60+1) = 1/61.
    # WITHOUT 1-based conversion this would be 1/(60+0) = 1/60 (Pitfall 5 — divide-by-zero
    # avoided but mathematically wrong vs. Cormack 2009).
    result = _rrf_fuse([("c1", 0, 1.0)], [])
    assert len(result) == 1
    assert result[0][0] == "c1"
    assert result[0][1] == pytest.approx(1.0 / 61.0)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-03 (docintel_retrieve.fuse.RRF_K)")
def test_rrf_k_constant() -> None:
    """RET-01 — RRF_K pinned at 60 (D-07; Cormack 2009 default; Plan 05-03)."""
    from docintel_retrieve.fuse import RRF_K  # noqa: WPS433 — intentional in-function import

    assert RRF_K == 60
