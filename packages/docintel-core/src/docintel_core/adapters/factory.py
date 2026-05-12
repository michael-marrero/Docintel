"""Factory that constructs an AdapterBundle from Settings.

The ONLY place in the codebase that instantiates concrete adapters.
Lazy imports inside the ``real`` branch keep stub-mode CI free of
torch / sentence-transformers / SDK import cost (D-12).

stub mode: deterministic stubs, no external deps.
real mode: lazy-imports torch + SDK deps; constructs real adapters per
           cfg.llm_real_provider; judge always uses the complement provider (D-04).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docintel_core.adapters.stub.embedder import StubEmbedder
from docintel_core.adapters.stub.reranker import StubReranker
from docintel_core.adapters.types import AdapterBundle

# TYPE_CHECKING guard: these imports run only under mypy/pyright, never at runtime.
# The real adapter modules (Wave 4) do not exist yet; this guard keeps mypy happy
# for the type annotations in make_adapters() without importing non-existent modules.
if TYPE_CHECKING:
    from docintel_core.adapters.real.judge import CrossFamilyJudge
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter
    from docintel_core.config import Settings


def make_adapters(cfg: Settings) -> AdapterBundle:
    """Construct and return an AdapterBundle keyed on cfg.llm_provider.

    stub mode: returns deterministic stub adapters with no external deps.
    real mode: lazily imports torch + SDK modules; dispatches per
               cfg.llm_real_provider; judge always uses the complement
               provider to avoid circular-judge bias (D-04).

    Args:
        cfg: Settings instance with llm_provider (and optionally llm_real_provider) set.

    Returns:
        AdapterBundle with embedder, reranker, llm, and judge adapters.
    """
    if cfg.llm_provider == "stub":
        from docintel_core.adapters.stub.judge import StubLLMJudge
        from docintel_core.adapters.stub.llm import StubLLMClient

        return AdapterBundle(
            embedder=StubEmbedder(),
            reranker=StubReranker(),
            llm=StubLLMClient(),
            judge=StubLLMJudge(),
        )

    # Real branch — lazy imports keep stub-mode CI free of SDK import cost (D-12).
    # These imports will raise ImportError until Wave 4 ships the real adapter modules.
    from docintel_core.adapters.real.embedder_bge import BGEEmbedder
    from docintel_core.adapters.real.judge import CrossFamilyJudge
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter
    from docintel_core.adapters.real.reranker_bge import BGEReranker

    # Cross-family judge dispatch (D-04): generator and judge always use DIFFERENT providers.
    # Avoids circular-judge bias where a model rubber-stamps its own output.
    llm: AnthropicAdapter | OpenAIAdapter
    judge_inner: OpenAIAdapter | AnthropicAdapter
    if cfg.llm_real_provider == "anthropic":
        llm = AnthropicAdapter(cfg)
        judge_inner = OpenAIAdapter(cfg)
    else:
        llm = OpenAIAdapter(cfg)
        judge_inner = AnthropicAdapter(cfg)

    judge: CrossFamilyJudge = CrossFamilyJudge(judge_inner, cfg)

    return AdapterBundle(
        embedder=BGEEmbedder(cfg),
        reranker=BGEReranker(cfg),
        llm=llm,
        judge=judge,
    )
