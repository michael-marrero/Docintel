"""Pydantic data-transfer models for the docintel adapter layer.

CD-05 decision: All adapter DTOs live here in adapters/types.py, separate from
the domain types in docintel_core/types.py (which carries Chunk, Citation, Answer
from later phases).

D-05: CompletionResponse carries text, usage (TokenUsage), cost_usd, latency_ms,
      and model for Phase 9 cost/latency metrics (MET-05).
D-07: JudgeVerdict carries score [0,1], passed bool, reasoning str, and
      unsupported_claims list for Phase 9 faithfulness (MET-03) and citation
      accuracy (MET-04).
CD-04: RerankedDoc is a Pydantic model (doc_id, text, score, original_rank) for
       clarity in Phase 5 ablation reports.
D-13: AdapterBundle holds all four Protocol-typed fields. arbitrary_types_allowed
      is REQUIRED because Pydantic v2 cannot build a schema for Protocol types
      (pydantic issue #10161). Bundle is constructed only by make_adapters()
      (Wave 3) — no external untrusted caller.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TokenUsage(BaseModel):
    """Token counts from a single LLM call.

    Maps both Anthropic (input_tokens/output_tokens) and OpenAI
    (prompt_tokens/completion_tokens) to a common schema.
    """

    prompt_tokens: int
    completion_tokens: int


class CompletionResponse(BaseModel):
    """Structured return type from LLMClient.complete().

    Phase 9 reads cost_usd and latency_ms directly for MET-05 ($/query,
    p50/p95 latency). Phase 10 reads model for the eval manifest header.
    """

    text: str
    usage: TokenUsage
    cost_usd: float
    latency_ms: float
    model: str


class JudgeVerdict(BaseModel):
    """Structured return type from LLMJudge.judge().

    score: float in [0.0, 1.0] — used for Wilson CIs in Phase 9 (MET-03).
    passed: bool — used for pass-rate metrics (MET-04).
    reasoning: human-readable explanation surfaced in eval reports.
    unsupported_claims: list of claim identifiers with no grounding reference.
    """

    score: float  # [0.0, 1.0]
    passed: bool
    reasoning: str
    unsupported_claims: list[str]


class RerankedDoc(BaseModel):
    """A single document after reranking, with its relevance score.

    doc_id: str placeholder in Phase 2; Phase 4 passes real chunk IDs
            through the same str slot.
    original_rank: zero-based position before reranking (for ablation deltas).
    """

    doc_id: str
    text: str
    score: float
    original_rank: int


# AdapterBundle — arbitrary_types_allowed REQUIRED for Protocol-typed fields.
# The runtime import of protocols is placed here (just above AdapterBundle)
# to minimise the visible cycle: protocols.py imports types.py under
# TYPE_CHECKING only; types.py imports protocols.py at runtime only for this
# one class. Wave 3's factory.py constructs AdapterBundle; callers never do.
from docintel_core.adapters.protocols import (  # noqa: E402
    Embedder,
    LLMClient,
    LLMJudge,
    Reranker,
)


class AdapterBundle(BaseModel):
    """Container for all four adapter instances returned by make_adapters(cfg).

    model_config uses arbitrary_types_allowed=True because Pydantic v2 cannot
    build a schema for Protocol types (github.com/pydantic/pydantic/issues/10161).
    Fields are stored as-is and not validated by Pydantic at construction time.
    Wave 3's make_adapters() is the only construction site.

    Phase 10 manifest header reads:
        bundle.embedder.name, bundle.reranker.name, bundle.llm.name, bundle.judge.name
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    embedder: Embedder
    reranker: Reranker
    llm: LLMClient
    judge: LLMJudge
