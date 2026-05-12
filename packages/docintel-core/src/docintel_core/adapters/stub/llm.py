"""Deterministic stub LLMClient -- templated synthesis with chunk_id citations.

Emits a templated synthesis response quoting chunk_id tokens found in the
prompt (pattern: bracket-enclosed identifiers). Emits refusal text when no
chunk IDs are present (GEN-04 path).
cost_usd=0.0, latency_ms=0.0, model='stub' (D-16).

The chunk_id regex is locked to the bracket-pattern for forward compatibility
with Phase 6 prompt schema formalisation (RESEARCH.md §Stub Determinism).

No randomness, no clock reads (ADP-07).
No retry wrapping -- stubs never make network calls. The CI grep gate for
tenacity is scoped to adapters/real/ only.
"""

from __future__ import annotations

import re
from typing import Final

from docintel_core.adapters.types import CompletionResponse, TokenUsage

_STUB_REFUSAL: Final[str] = "[STUB REFUSAL] No evidence found in retrieved context."
"""Canonical refusal string for the no-chunk path (GEN-04).

Phase 6 may replace this constant when formalising the prompt schema and
refusal contract. Phase 2 locks this text so Phase 9 stub-mode faithfulness
tests have a stable, predictable refusal sentinel.
"""

_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")
"""Module-level compiled regex for extracting [chunk_id] tokens.

Pattern is locked here for forward compatibility: Phase 6 introduces the
formal prompt schema; Phase 9 faithfulness tests rely on the same regex
producing the same citation extractions in stub and real modes.
"""


class StubLLMClient:
    """Deterministic stub LLMClient for stub/CI mode.

    Satisfies the LLMClient Protocol structurally (no inheritance).
    Extracts [chunk_id] tokens from the prompt and emits a templated
    synthesis response citing them. Falls back to _STUB_REFUSAL when
    the prompt contains no chunk IDs.
    Deterministic: identical inputs always produce identical outputs.
    No external dependencies.
    """

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "stub-llm"

    def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> CompletionResponse:
        """Generate a stub completion for the given prompt.

        If the prompt contains [chunk_id] tokens (per Phase 6 schema), emits
        a templated synthesis response quoting those IDs. Otherwise emits the
        canonical _STUB_REFUSAL string.

        Token counts use whitespace-split approximation (deterministic).
        cost_usd=0.0, latency_ms=0.0, model='stub' (D-16).

        Args:
            prompt: The user-facing prompt text.
            system: Ignored in stub mode (accepted for Protocol conformance).

        Returns:
            CompletionResponse with deterministic text, usage, zero cost/latency.
        """
        chunk_ids = _CHUNK_RE.findall(prompt)
        if not chunk_ids:
            text = _STUB_REFUSAL
        else:
            text = (
                f"Based on the provided context: {prompt[:200]}... "
                f"[STUB ANSWER citing {chunk_ids}]"
            )
        prompt_tokens = len(prompt.split())
        completion_tokens = len(text.split())
        return CompletionResponse(
            text=text,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            cost_usd=0.0,
            latency_ms=0.0,
            model="stub",
        )
