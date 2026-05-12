"""Real LLMClient backed by the Anthropic messages API (claude-sonnet-4-6).

Model: claude-sonnet-4-6 (default). API key is read from
Settings.anthropic_api_key.get_secret_value() exactly ONCE — in __init__,
at SDK client construction. It is NEVER logged, NEVER passed to tenacity
hooks, and NEVER stored in any field other than the SDK client object (SP-4,
T-02-05 mitigation).

Every client.messages.create() call is inside a tenacity @retry decorator
(ADP-06, D-18). The retry policy covers transient failures only:
RateLimitError (HTTP 429), APIConnectionError (network), APITimeoutError.
AuthenticationError and BadRequestError are NOT retried — they indicate a
configuration or input problem that won't resolve by retrying (T-02-01).

The anthropic exception classes (RateLimitError, APIConnectionError,
APITimeoutError) are imported at module top-level so they are available
when Python evaluates the @retry(...) decorator at class definition time.
This is safe because this module is only imported inside make_adapters()'s
real branch (factory.py), which executes only when cfg.llm_provider == 'real'.
"""

from __future__ import annotations

import logging
import time

import structlog
from anthropic import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_core.adapters.types import CompletionResponse, TokenUsage
from docintel_core.config import Settings
from docintel_core.pricing import cost_for

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_log;
# structlog bound logger for all other structured log lines.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2048


class AnthropicAdapter:
    """Real LLMClient adapter wrapping the Anthropic messages API.

    Satisfies the LLMClient Protocol structurally (no inheritance required).
    Default model: claude-sonnet-4-6. The factory dispatches to this adapter
    when cfg.llm_real_provider == 'anthropic'.

    D-03: Both AnthropicAdapter and OpenAIAdapter ship as real adapters behind
    the same LLMClient Protocol — the 'seam is the artifact' demonstration.
    """

    def __init__(self, cfg: Settings) -> None:
        """Construct SDK client using the API key from Settings.

        SP-4 / T-02-05: .get_secret_value() is called EXACTLY ONCE here.
        The raw key string is passed directly to the SDK client constructor
        and not stored, logged, or referenced anywhere else in this file.

        Args:
            cfg: Settings instance with anthropic_api_key set.

        Raises:
            ValueError: If cfg.anthropic_api_key is None (required for real mode).
        """
        import anthropic  # lazy — only executed when real branch runs

        if cfg.anthropic_api_key is None:
            raise ValueError(
                "DOCINTEL_ANTHROPIC_API_KEY is required when llm_provider='real'"
            )
        # SP-4: the ONLY call to .get_secret_value() in this file.
        self._client = anthropic.Anthropic(
            api_key=cfg.anthropic_api_key.get_secret_value()
        )
        self._model = _DEFAULT_MODEL
        log.info("anthropic_adapter_initialized", model=self._model)

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return self._model

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> CompletionResponse:
        """Generate a completion via the Anthropic messages API.

        Measures wall-clock latency from just before the API call to just after.
        Maps Anthropic's input_tokens/output_tokens to the shared TokenUsage schema.
        Calls cost_for() which raises KeyError if the model is not in PRICING (T-02-04).

        Args:
            prompt: The user-facing prompt text.
            system: Optional system/instruction prompt. Defaults to a generic assistant
                    instruction when None. Phase 6 will supply structured system prompts
                    from generation/prompts.py (GEN-01).

        Returns:
            CompletionResponse with text, usage, cost_usd, latency_ms, and model.
        """
        t0 = time.perf_counter()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        # Anthropic SDK: input_tokens / output_tokens (differs from OpenAI)
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        cost = cost_for("anthropic", self._model, usage.prompt_tokens, usage.completion_tokens)

        return CompletionResponse(
            text=response.content[0].text,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            model=response.model,
        )
