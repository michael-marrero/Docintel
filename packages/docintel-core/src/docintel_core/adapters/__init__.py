"""Public re-export surface for docintel_core.adapters.

D-10: All four Protocol classes, the Pydantic DTOs, and AdapterBundle are
importable directly from docintel_core.adapters. make_adapters() is NOT
exported here yet — Wave 3 (Plan 02-04) appends that line when factory.py
ships.

Usage:
    from docintel_core.adapters import Embedder, AdapterBundle, CompletionResponse
    from docintel_core.adapters.protocols import Reranker  # fine too
"""

from __future__ import annotations

from docintel_core.adapters.protocols import (
    Embedder,
    LLMClient,
    LLMJudge,
    Reranker,
)
from docintel_core.adapters.types import (
    AdapterBundle,
    CompletionResponse,
    JudgeVerdict,
    RerankedDoc,
    TokenUsage,
)

__all__ = [
    "AdapterBundle",
    "CompletionResponse",
    "Embedder",
    "JudgeVerdict",
    "LLMClient",
    "LLMJudge",
    "RerankedDoc",
    "Reranker",
    "TokenUsage",
]
