"""Factory that constructs an AdapterBundle from Settings.

The ONLY place in the codebase that instantiates concrete adapters.
Wave 2 ships stub-only support. Wave 3 (02-04) extends this with the real
branch, Settings.llm_real_provider dispatch, and lazy SDK imports (D-12).

Lazy imports inside the ``real`` branch keep stub-mode CI free of
torch / sentence-transformers / SDK import cost (D-12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docintel_core.adapters.stub.embedder import StubEmbedder
from docintel_core.adapters.stub.reranker import StubReranker

if TYPE_CHECKING:
    from docintel_core.config import Settings


def make_adapters(cfg: Settings) -> object:
    """Construct and return an AdapterBundle keyed on cfg.llm_provider.

    stub mode: returns deterministic stub adapters with no external deps.
    real mode: raises NotImplementedError until Wave 3 ships real adapters.

    Args:
        cfg: Settings instance with llm_provider field.

    Returns:
        AdapterBundle with embedder, reranker, llm, judge adapters.
    """
    from docintel_core.adapters.types import AdapterBundle

    if cfg.llm_provider == "stub":
        from docintel_core.adapters.stub.judge import StubLLMJudge
        from docintel_core.adapters.stub.llm import StubLLMClient

        return AdapterBundle(
            embedder=StubEmbedder(),
            reranker=StubReranker(),
            llm=StubLLMClient(),
            judge=StubLLMJudge(),
        )

    # Real branch -- Wave 3 (02-04) implements this with lazy imports.
    raise NotImplementedError(
        "Real adapter branch not yet implemented. "
        "Set DOCINTEL_LLM_PROVIDER=stub for stub mode. "
        "Wave 3 (02-04) ships the real branch with AnthropicAdapter, "
        "OpenAIAdapter, BGEEmbedder, BGEReranker, and CrossFamilyJudge."
    )
