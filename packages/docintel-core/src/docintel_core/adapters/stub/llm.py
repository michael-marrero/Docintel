"""Deterministic stub LLMClient -- templated synthesis with chunk_id citations.

Emits a templated synthesis response quoting chunk_id tokens found in the
prompt (pattern: bracket-enclosed identifiers). Emits refusal text when no
chunk IDs are present (GEN-04 path).
cost_usd=0.0, latency_ms=0.0, model='stub' (D-16).

The chunk_id regex and refusal sentinel are imported from the canonical
Phase 6 homes (``docintel_generate.parse._CHUNK_RE`` and
``docintel_core.types.REFUSAL_TEXT_SENTINEL`` respectively); this module
re-aliases them as ``_CHUNK_RE`` and ``_STUB_REFUSAL`` for backward-compat
with existing tests + Phase 2 D-16 contract.

No randomness, no clock reads (ADP-07).
No retry wrapping -- stubs never make network calls. The CI grep gate for
tenacity is scoped to adapters/real/ only.
"""

from __future__ import annotations

from typing import Final

from docintel_core.adapters.types import CompletionResponse, TokenUsage
from docintel_core.types import REFUSAL_TEXT_SENTINEL

# D-12: single canonical _CHUNK_RE home is docintel_generate.parse. The Pitfall 9
# cycle concern (stub-in-core importing from generate-package) is acknowledged:
# this is the ONE stub import allowed to cross packages (CONTEXT.md D-12 line 107).
# The cycle is one-way at runtime — make_adapters() returns the stub only when
# llm_provider="stub", at which point docintel-generate is already loaded.
from docintel_generate.parse import _CHUNK_RE

_STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL
"""Backward-compat alias for the canonical refusal sentinel.

Phase 6 D-11 + D-12 promotion: this constant now mirrors
``docintel_core.types.REFUSAL_TEXT_SENTINEL`` verbatim — the same 63-char
string the Generator emits on hard refusal (Step B of D-15). The Phase 2
bracketed-placeholder text is retired; stub-mode pytest + Phase 9
faithfulness tests now see the SAME byte-string in both stub and real
modes (RESEARCH Pitfall 5 mitigation).

The ``_STUB_REFUSAL`` name is retained for backward-compatibility of any
existing test imports (tests assert against the symbol, not the byte-literal
old value). New code should import ``REFUSAL_TEXT_SENTINEL`` from
``docintel_core.types`` directly.
"""

# `_CHUNK_RE` is no longer defined here — it is imported above from
# ``docintel_generate.parse`` (D-12 single source of truth across stub +
# real + Phase 7 Citation parser). Python's name resolution lets the
# existing ``_CHUNK_RE.findall(prompt)`` call at module-scope resolve to
# the imported Pattern instance without source changes inside the class.


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
        raw_matches = _CHUNK_RE.findall(prompt)
        # D-14 context-block headers have shape:
        #   [chunk_id: AAPL-FY2024-Item-1A-018 | company: AAPL | fiscal_year: 2024 | section: Item 1A]
        # The Generator's Step D regex extracts the WHOLE bracket content,
        # but the validated chunk_id set carries the BARE id. Extract the bare
        # id from each header so the stub's emitted citations match the
        # retrieved-chunks set. Bare-bracket prompts (`[AAPL-FY2024-Item-1A-018]`
        # from older tests) pass through unchanged.
        chunk_ids: list[str] = []
        for match in raw_matches:
            if match.startswith("chunk_id:"):
                first_pair = match.split("|", 1)[0]
                bare = first_pair.split(":", 1)[1].strip()
                chunk_ids.append(bare)
            else:
                chunk_ids.append(match)
        if not chunk_ids:
            text = _STUB_REFUSAL
        else:
            # Emit each chunk_id as a separate bare `[chunk_id]` token so the
            # Generator's `_CHUNK_RE.findall(text)` (D-13 step 3) correctly
            # extracts every cited id. The Phase 2 placeholder emitted
            # `[STUB ANSWER citing [<list-repr>]]` which the regex captured
            # as a single nested match — Phase 6 Pitfall 5 fix.
            citations = " ".join(f"[{cid}]" for cid in chunk_ids)
            text = (
                f"Stub synthesis grounded in the provided context. "
                f"Citations: {citations}"
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
