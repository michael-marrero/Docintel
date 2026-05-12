"""Real adapter implementations for docintel -- requires external dependencies.

This subpackage requires sentence-transformers, anthropic SDK, and openai SDK.
It is imported LAZILY by factory.py only when cfg.llm_provider == "real" (D-12).
Stub-mode CI never pays the torch or SDK import cost because this subpackage
is not imported at the module top level.

Every external call in each real adapter is wrapped in the tenacity retry
decorator with before-sleep logging (D-18, ADP-06). Wave 4 of Phase 2 fills
this package with the concrete real adapters:
  real/embedder_bge.py  -- BGEEmbedder (sentence-transformers, BAAI/bge-small-en-v1.5)
  real/reranker_bge.py  -- BGEReranker (CrossEncoder, BAAI/bge-reranker-base)
  real/llm_anthropic.py -- AnthropicAdapter (anthropic SDK, claude-sonnet-4-6)
  real/llm_openai.py    -- OpenAIAdapter (openai SDK, gpt-4o)
  real/llm_judge.py     -- CrossFamilyJudge (cross-family to avoid circular bias, D-04)

Note on grep gate (Wave 4, D-18): scripts/check_adapter_wraps.sh checks each
real adapter file for evidence that the tenacity @retry decorator is present.
This docstring intentionally uses only prose descriptions of retry patterns
rather than the exact import token that the gate script greps for, to prevent
self-satisfying the gate and masking a missing retry import in a sibling file.
"""

from __future__ import annotations
