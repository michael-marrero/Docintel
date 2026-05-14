"""Phase 5 implementation — hybrid retrieval (BM25 + dense via RRF) + cross-encoder rerank seam.

Composes Phase 2 `AdapterBundle` + Phase 4 `IndexStoreBundle` into a single
`Retriever.search(query, k) -> list[RetrievedChunk]` seam.

See `docintel_retrieve.retriever` for the orchestrator class;
`docintel_retrieve.fuse` for the pure RRF helper;
`docintel_retrieve.null_adapters` for the Phase 11 ablation seam
(NullReranker + NullBM25Store).

Public surface is built up incrementally across Plans 05-02..05-05:
- Plan 05-02 Task 2 adds RetrievedChunk re-export (atomic with the class itself).
- Plan 05-03 adds RRF_K + _rrf_fuse re-exports.
- Plan 05-04 adds NullReranker + NullBM25Store re-exports.
- Plan 05-05 adds Retriever re-export.
"""

from docintel_core.types import RetrievedChunk

from docintel_retrieve.fuse import RRF_K, _rrf_fuse

__all__ = ["RRF_K", "RetrievedChunk", "_rrf_fuse"]
