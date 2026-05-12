"""Real LLMClient backed by the OpenAI chat completions API (gpt-4o default).

Model: gpt-4o (default). Fallback: gpt-4.1 (both in pricing table — D-06).
API key is read from Settings.openai_api_key.get_secret_value() exactly
ONCE — in __init__, at SDK client construction. It is NEVER logged, NEVER
passed to tenacity hooks, and NEVER stored in any field other than the SDK
client object (SP-4, T-02-05 mitigation).

Every client.chat.completions.create() call is inside a tenacity @retry
decorator (ADP-06, D-18). The retry policy covers transient failures only:
RateLimitError (HTTP 429), APIConnectionError (network), APITimeoutError.
AuthenticationError and BadRequestError are NOT retried (T-02-01).

Key structural difference from llm_anthropic.py:
- System prompt is inside the messages list (role='system') NOT a top-level arg
- Usage fields: response.usage.prompt_tokens / completion_tokens (not input_/output_)
- Response text: response.choices[0].message.content (not response.content[0].text)

The openai exception classes (RateLimitError, APIConnectionError, APITimeoutError)
are imported at module top-level so they are available when Python evaluates
the @retry(...) decorator at class definition time. This is safe because this
module is only imported inside make_adapters()'s real branch.
"""

from __future__ import annotations

import logging
import time

import structlog
from openai import APIConnectionError, APITimeoutError, RateLimitError
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

_DEFAULT_MODEL = "gpt-4o"
_MAX_TOKENS = 2048


class OpenAIAdapter:
    """Real LLMClient adapter wrapping the OpenAI chat completions API.

    Satisfies the LLMClient Protocol structurally (no inheritance required).
    Default model: gpt-4o. The factory dispatches to this adapter when
    cfg.llm_real_provider == 'openai', or uses it as the judge complement
    when llm_real_provider == 'anthropic' (D-03, D-04).

    D-03: Both OpenAIAdapter and AnthropicAdapter ship as real adapters behind
    the same LLMClient Protocol — the 'seam is the artifact' demonstration.
    """

    def __init__(self, cfg: Settings) -> None:
        """Construct SDK client using the API key from Settings.

        SP-4 / T-02-05: .get_secret_value() is called EXACTLY ONCE here.
        The raw key string is passed directly to the SDK client constructor
        and not stored, logged, or referenced anywhere else in this file.

        Args:
            cfg: Settings instance with openai_api_key set.

        Raises:
            ValueError: If cfg.openai_api_key is None (required for real mode).
        """
        import openai  # lazy — only executed when real branch runs

        if cfg.openai_api_key is None:
            raise ValueError(
                "DOCINTEL_OPENAI_API_KEY is required when llm_provider='real'"
            )
        # SP-4: the ONLY call to .get_secret_value() in this file.
        self._client = openai.OpenAI(
            api_key=cfg.openai_api_key.get_secret_value()
        )
        self._model = _DEFAULT_MODEL
        log.info("openai_adapter_initialized", model=self._model)

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
        """Generate a completion via the OpenAI chat completions API.

        Structural difference from AnthropicAdapter: system prompt goes inside
        the messages list as a dict with role='system' (not a top-level param).
        Usage fields are prompt_tokens/completion_tokens (not input_/output_).

        Args:
            prompt: The user-facing prompt text.
            system: Optional system/instruction prompt. Defaults to a generic assistant
                    instruction when None. Phase 6 will supply structured system prompts
                    from generation/prompts.py (GEN-01).

        Returns:
            CompletionResponse with text, usage, cost_usd, latency_ms, and model.
        """
        t0 = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        # OpenAI SDK: prompt_tokens / completion_tokens (differs from Anthropic)
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        cost = cost_for("openai", self._model, usage.prompt_tokens, usage.completion_tokens)

        return CompletionResponse(
            text=response.choices[0].message.content or "",
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            model=response.model,
        )
