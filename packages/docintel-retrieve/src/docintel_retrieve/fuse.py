"""Reciprocal Rank Fusion (Cormack et al. 2009) -- pure helper.

The standard hybrid-search rank combiner. The formula is:

    rrf_score(chunk_id) = sum over rankers r of [ 1 / (k + rank_r(chunk_id)) ]

where ``rank_r`` is 1-based (a chunk at position 0 in the result list has
rank 1). The literature convention is 1-based; Phase 4's `BM25Store.query()`
and `DenseStore.query()` return 0-based ranks (the top result has rank=0),
so `_rrf_fuse` performs the `rank + 1` conversion explicitly inside the
function. Pitfall 5: using 0-based ranks here would still produce an
ordering consistent with rerank intent, but absolute RRF scores would
differ from literature values that Phase 9/11 reports compare against.

If a chunk does NOT appear in ranker r's top-N, it contributes ZERO to its
RRF score from that ranker (not ``1/(k + infinity)`` -- the formula is
undefined there; the production pattern is "skip the contribution when the
chunk is missing"). [VERIFIED across LangChain ``EnsembleRetriever``,
LlamaIndex ``QueryFusionRetriever``, OpenSearch ``rrf`` retriever, and
Elastic ``rrf`` retriever -- all use skip-the-contribution.]

Tie-breaking (CD-05): when two chunks have identical RRF scores, sort by
BM25 rank ascending (the chunk that appeared higher in BM25 wins) -- the
lexical match is more interpretable when citations are surfaced. A chunk
missing from the BM25 list uses ``float("inf")`` as its sentinel BM25 rank,
which pushes it after any BM25-present chunk in a tie.

Pure-function statement: no I/O, no Settings, no logging. Phase 11 ablation
reports replay this function over saved per-stage outputs to diff fusion
behaviour across runs without re-running retrieval.

Citation: Cormack, Clarke, Buettcher. "Reciprocal Rank Fusion outperforms
Condorcet and individual rank learning methods." SIGIR 2009.
https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
"""

from __future__ import annotations

from typing import Final

RRF_K: Final[int] = 60
"""Cormack 2009 default. Pinned module constant per D-07. NOT a Settings field."""


def _rrf_fuse(
    bm25_results: list[tuple[str, int, float]],
    dense_results: list[tuple[str, int, float]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Combine two rank lists into one via Reciprocal Rank Fusion.

    Args:
        bm25_results: ``[(chunk_id, rank, score)]`` from ``Bm25sStore.query``.
            ``rank`` is 0-based per the Phase 4 BM25Store contract.
        dense_results: ``[(chunk_id, rank, score)]`` from ``DenseStore.query``.
            ``rank`` is 0-based per the Phase 4 DenseStore contract
            (NumpyDenseStore + QdrantDenseStore both honour the convention).
        k: RRF smoothing constant. Default ``RRF_K`` = 60 (Cormack 2009);
            pinned per D-07.

    Returns:
        ``[(chunk_id, rrf_score)]`` sorted descending by ``rrf_score``, with
        BM25-rank ascending as the tie-break (CD-05). Output length equals
        the number of unique ``chunk_id`` values across both input lists
        (set-union cardinality). Empty inputs yield ``[]`` (no exception).

    Note:
        Pitfall 5 (0-vs-1-based ranks): the function converts 0-based input
        ranks to 1-based in the formula. A chunk at 0-based rank 0 in BM25
        only contributes ``1/(k + 1)``, not ``1/(k + 0)``.
    """
    # Convert 0-based ranks to 1-based for the RRF formula (Pitfall 5).
    # A chunk at 0-based rank 0 in BM25 contributes 1/(k + 1), matching the
    # literature convention that Phase 9/11 reports compare against.
    bm25_ranks: dict[str, int] = {cid: rank + 1 for cid, rank, _ in bm25_results}
    dense_ranks: dict[str, int] = {cid: rank + 1 for cid, rank, _ in dense_results}

    # Skip-the-contribution-when-missing pattern (RESEARCH.md Section 1).
    # Each chunk gets the sum of 1/(k + rank) over the rankers that returned
    # it; rankers that did NOT return it contribute zero. Production pattern
    # across LangChain, LlamaIndex, OpenSearch, and Elastic.
    all_chunk_ids = set(bm25_ranks) | set(dense_ranks)
    rrf_scores: dict[str, float] = {}
    for cid in all_chunk_ids:
        score = 0.0
        if cid in bm25_ranks:
            score += 1.0 / (k + bm25_ranks[cid])
        if cid in dense_ranks:
            score += 1.0 / (k + dense_ranks[cid])
        rrf_scores[cid] = score

    # Sort descending by RRF score; tie-break by BM25 rank ascending (CD-05).
    # A chunk not in bm25_ranks gets float("inf") as its sentinel rank,
    # pushing BM25-missing chunks after any BM25-present chunk in a tie.
    def _sort_key(cid: str) -> tuple[float, float]:
        # Negate the score so ascending sort produces descending order.
        bm25_rank: float = bm25_ranks.get(cid, float("inf"))
        return (-rrf_scores[cid], bm25_rank)

    return [(cid, rrf_scores[cid]) for cid in sorted(rrf_scores, key=_sort_key)]
