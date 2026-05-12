"""Public re-export surface for docintel_core.adapters.

D-10: All four Protocol classes, the Pydantic DTOs, AdapterBundle, and
make_adapters() are importable directly from docintel_core.adapters.

Usage:
    from docintel_core.adapters import Embedder, AdapterBundle, CompletionResponse
    from docintel_core.adapters import make_adapters
    from docintel_core.adapters.protocols import Reranker  # fine too
"""

from __future__ import annotations

from docintel_core.adapters.factory import make_adapters
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
    "make_adapters",
]
