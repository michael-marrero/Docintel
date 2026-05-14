"""Public re-export surface for docintel_core.adapters.

D-10: All four Protocol classes, the Pydantic DTOs, AdapterBundle, and
make_adapters() are importable directly from docintel_core.adapters.

Phase 4 D-02 + D-03 amendment: DenseStore + BM25Store Protocols and
IndexStoreBundle Pydantic model are re-exported here so Plan 04-04's
store-adapter implementations and Plan 04-05's ``build_indices`` /
``verify_indices`` can import from the single canonical surface.

Usage:
    from docintel_core.adapters import Embedder, AdapterBundle, CompletionResponse
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters import DenseStore, BM25Store, IndexStoreBundle
    from docintel_core.adapters.protocols import Reranker  # fine too
"""

from __future__ import annotations

from docintel_core.adapters.factory import make_adapters, make_retriever
from docintel_core.adapters.protocols import (
    BM25Store,
    DenseStore,
    Embedder,
    LLMClient,
    LLMJudge,
    Reranker,
)
from docintel_core.adapters.types import (
    AdapterBundle,
    CompletionResponse,
    IndexStoreBundle,
    JudgeVerdict,
    RerankedDoc,
    TokenUsage,
)

__all__ = [
    "AdapterBundle",
    "BM25Store",
    "CompletionResponse",
    "DenseStore",
    "Embedder",
    "IndexStoreBundle",
    "JudgeVerdict",
    "LLMClient",
    "LLMJudge",
    "RerankedDoc",
    "Reranker",
    "TokenUsage",
    "make_adapters",
    "make_retriever",
]
