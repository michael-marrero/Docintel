"""Sanitizing ``before_sleep`` factory for tenacity ``@retry`` decorators.

EMP-05 / Phase 14 D-04 / D-05 — closes ``P-EMP-04`` ("API-key leakage on
retry-path log"). Real adapters wrap every SDK call with the tenacity
``@retry`` decorator per CLAUDE.md "no silent retries on LLM calls";
the canonical tenacity before-sleep callback passes ``str(exception)``
verbatim into a stdlib ``logger.log(...)`` line. If an SDK exception ever surfaces an
``Authorization`` header or a raw API key (many SDKs do, in 401/403
paths), the canonical factory writes that secret straight into committed
CI logs.

This module's :func:`before_sleep_safe` is the drop-in replacement:
verbatim semantics of tenacity 9.1.4's vendored ``before_sleep`` factory
(see ``before_sleep.py`` lines 29-71 in the installed package, which is
the upstream reference shape) including the ``RuntimeError`` None-guards
on ``retry_state.outcome`` and ``retry_state.next_action`` (RESEARCH
Pitfall 3), but applies :data:`_REDACT_PATTERN` to ``str(exception)``
(and ``str(result)`` on the success branch — belt-and-suspenders) before
delegating to ``logger.log(level, ...)``.

D-05 regex ordering rule: ``sk-ant-`` MUST precede ``sk-`` in the
alternation. Without that ordering, a real Anthropic key would partial-
match the OpenAI branch and emit ``[REDACTED:sk-]`` instead of
``[REDACTED:sk-ant-]``. The 20-character minimum after each prefix
prevents the regex from scrubbing 40-character git SHAs or short
request IDs that happen to embed similar substrings.

D-04 module-name convention: the leading underscore on ``_logging.py``
keeps this symbol internal to ``adapters/real/`` (NOT a public export
from ``docintel-core``). Plan 14-04 sweeps the 12 raw use-sites across 6
adapter files (per RESEARCH Pitfall 1 corrected count) to
``before_sleep_safe(...)`` and lands the
``scripts/check_before_sleep_safe.sh`` CI gate that enforces
"zero raw before-sleep-log call survives in adapters/real/" (D-06).

D-04 SP-3 scope: this module wraps only the stdlib-logger path that
tenacity uses for before-sleep. The structured-event path (the other
logger that every real adapter binds at module-import time) is
intentionally NOT touched here — the sanitizer never emits structured
events, and importing the structured-logger library would create the
appearance of dual responsibility where there is one.
"""

from __future__ import annotations

import logging
import re
import typing

from tenacity._utils import get_callback_name

if typing.TYPE_CHECKING:
    from tenacity import RetryCallState


# D-05 redaction regex.
#
# Ordering matters: ``sk-ant-`` precedes ``sk-`` so that a real
# Anthropic key (``sk-ant-XXXXXXXXXXXXXXXXXXXX``) is matched by the
# longer prefix first. If reversed, ``sk-`` would partial-match the
# Anthropic key and emit the wrong ``[REDACTED:sk-]`` marker.
#
# The ``{20,}`` quantifier after each prefix is what keeps 40-char
# git SHAs (no recognized prefix) and short request IDs from being
# scrubbed. ``sk-short`` (8 chars total) is NOT redacted.
#
# ``Bearer\s+[a-zA-Z0-9.\-_~+/]{20,}=*`` matches HTTP Authorization
# headers carrying any 20+-char base64url-ish token (covers JWTs,
# OAuth bearer tokens, and any SDK-surfaced ``Bearer XXX`` substring).
_REDACT_PATTERN: re.Pattern[str] = re.compile(
    r"(sk-ant-[a-zA-Z0-9-_]{20,}|sk-[a-zA-Z0-9-_]{20,}|pa-[a-zA-Z0-9-_]{20,}|Bearer\s+[a-zA-Z0-9.\-_~+/]{20,}=*)"
)


def _redact(text: str) -> str:
    """Replace each ``_REDACT_PATTERN`` match in ``text`` with a typed marker.

    The marker preserves the "an auth credential was here" signal without
    leaking content — useful for retry-path log archaeology where you want
    to know *whether* a 401 carried a key without exposing the key itself.

    Discrimination is by prefix on the matched substring:

    * ``sk-ant-...`` → ``[REDACTED:sk-ant-]`` (Anthropic)
    * ``sk-...``     → ``[REDACTED:sk-]``     (OpenAI; matched AFTER sk-ant-)
    * ``pa-...``     → ``[REDACTED:pa-]``     (Voyage)
    * ``Bearer ...`` → ``[REDACTED:Bearer]``  (any HTTP Authorization)
    * any other match (defensive — should never fire given the regex) →
      ``[REDACTED]``

    Args:
        text: Free-form string (typically ``str(exception)`` from a
            tenacity ``RetryCallState.outcome.exception()``) that may
            contain one or more credential substrings.

    Returns:
        The same text with each credential substring replaced by its
        typed marker. Non-credential content is returned verbatim.
    """

    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        # Order matters here too — check sk-ant- before sk-.
        if token.startswith("sk-ant-"):
            return "[REDACTED:sk-ant-]"
        if token.startswith("sk-"):
            return "[REDACTED:sk-]"
        if token.startswith("pa-"):
            return "[REDACTED:pa-]"
        if token.startswith("Bearer"):
            return "[REDACTED:Bearer]"
        return "[REDACTED]"

    return _REDACT_PATTERN.sub(_sub, text)


def before_sleep_safe(
    logger: logging.Logger,
    log_level: int,
) -> typing.Callable[["RetryCallState"], None]:
    """Tenacity ``before_sleep`` factory that redacts API-key patterns.

    Drop-in replacement for the canonical tenacity before-sleep factory.
    Mirrors the upstream semantics verbatim — including the
    ``RuntimeError`` guards on ``retry_state.outcome is None`` and
    ``retry_state.next_action is None`` (RESEARCH Pitfall 3) — but
    applies :func:`_redact` to the exception/result string before it
    reaches ``logger.log(...)``.

    Both the failure branch (``outcome.failed`` → ``str(exception)``)
    and the success branch (``str(outcome.result())``) are sanitized.
    The success branch redaction is belt-and-suspenders: tenacity's
    before-sleep only fires on retry (i.e., between a failed attempt
    and the next try), so the success path is structurally unreachable
    today; redacting it anyway costs one regex pass and forecloses a
    future surprise if tenacity changes that contract.

    Args:
        logger: stdlib ``logging.Logger`` to log to. The two-logger
            pattern (SP-3) keeps this on the stdlib path and never on
            the structured-event path.
        log_level: Numeric logging level (e.g., ``logging.WARNING``)
            passed verbatim to ``logger.log(...)``.

    Returns:
        A ``Callable[[RetryCallState], None]`` suitable for the
        ``before_sleep=`` argument of ``tenacity.retry(...)``. The
        closure name is ``log_it`` to match tenacity's canonical
        factory (helps recognizability in tracebacks).

    Raises (the returned closure raises, not this factory):
        RuntimeError: If invoked before tenacity has populated
            ``retry_state.outcome`` or ``retry_state.next_action``.
            Mirrors upstream's explicit-error contract — any caller
            that hand-builds a ``RetryCallState`` without those fields
            sees a clear ``RuntimeError`` instead of an opaque
            ``AttributeError``.
    """

    def log_it(retry_state: "RetryCallState") -> None:
        # Pitfall 3 None-guards — mirror tenacity's own contract verbatim.
        # Raising RuntimeError (not AttributeError) is what upstream
        # documents in its vendored before-sleep factory.
        if retry_state.outcome is None:
            raise RuntimeError(
                "before_sleep_safe called before outcome was set"
            )
        if retry_state.next_action is None:
            raise RuntimeError(
                "before_sleep_safe called before next_action was set"
            )

        if retry_state.outcome.failed:
            ex = retry_state.outcome.exception()
            verb = "raised"
            # ``str(ex)`` carries any embedded API key; sanitize before
            # it reaches the logger.
            value = _redact(f"{ex.__class__.__name__}: {ex}")
        else:
            # Belt-and-suspenders: tenacity's before-sleep does not fire
            # on success today, but redacting str(result) anyway costs
            # one regex pass and forecloses a future contract change.
            verb = "returned"
            value = _redact(str(retry_state.outcome.result()))

        fn_name = (
            get_callback_name(retry_state.fn)
            if retry_state.fn is not None
            else "<unknown>"
        )

        logger.log(
            log_level,
            f"Retrying {fn_name} in {retry_state.next_action.sleep:.3g} seconds as it {verb} {value}.",
        )

    return log_it
