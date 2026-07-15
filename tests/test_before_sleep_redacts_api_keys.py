"""EMP-05 D-05 redaction fixtures — green after Plan 14-03.

Confirms the 4 D-05 key shapes (``sk-``, ``sk-ant-``, ``pa-``, ``Bearer``)
are scrubbed to ``[REDACTED:<type>]`` before reaching the logger. The
20-char minimum keeps git SHAs and request IDs unscrubbed (D-05).

Parametrize order matters per CONTEXT.md D-05: ``sk-ant-`` MUST precede
``sk-`` so the regex's order-matters invariant is exercised (if a future
edit reorders the alternations, ``sk-ant-`` keys would partial-match the
``sk-`` branch and emit the wrong marker).

Lifecycle: Wave-0 (Plan 14-01) landed this as red xfail-strict while
``docintel_core.adapters.real._logging`` did not yet exist. Plan 14-03
landed the helper module + ``before_sleep_safe`` factory and removed
the xfail marker — these 4 cases now run green.

Pitfall 3 (14-RESEARCH.md lines 578-598): we drive the callable through a
real ``tenacity @retry`` decorator on a function that raises
``ValueError(planted)``. That way ``RetryCallState.outcome``,
``next_action``, and ``fn`` are all set non-None by tenacity itself, and we
do not mis-mock the canonical guards.

Analogs:
* 14-PATTERNS.md §"NEW tests/test_before_sleep_redacts_api_keys.py" lines
  302-331 (parametrize skeleton).
* 14-RESEARCH.md Pattern 1 (canonical tenacity before-sleep factory shape,
  source = ``tenacity/before_sleep.py:29-71``).
"""

from __future__ import annotations

import logging

import pytest
from tenacity import retry, stop_after_attempt, wait_fixed

# Imported lazily at call-time so collection does not break in Wave 0 while
# the module does not yet exist — the xfail marker swallows the ImportError.


@pytest.mark.parametrize(
    "planted,expected_marker",
    [
        # D-05: sk-ant- MUST precede sk- so order-matters invariant is exercised.
        (
            "Auth failed for sk-ant-1234567890abcdefghij1234567890abcdef",
            "[REDACTED:sk-ant-]",
        ),
        (
            "Auth failed for sk-1234567890abcdefghij1234567890abcdef",
            "[REDACTED:sk-]",
        ),
        (
            "Auth failed for pa-1234567890abcdefghij1234567890abcdef",
            "[REDACTED:pa-]",
        ),
        (
            "HTTP 401 Bearer abcdefghij1234567890abcdefghij1234567890=",
            "[REDACTED:Bearer]",
        ),
    ],
    ids=["sk-ant-", "sk-", "pa-", "Bearer"],
)
def test_redacts_each_pattern(
    caplog: pytest.LogCaptureFixture,
    planted: str,
    expected_marker: str,
) -> None:
    """EMP-05 / D-05: each D-05 pattern is scrubbed before reaching the logger.

    Drives a real tenacity ``@retry`` decorator on a function that raises
    ``ValueError(planted)`` after one attempt. The
    ``before_sleep=before_sleep_safe(...)`` callback fires between attempts
    with a fully-populated ``RetryCallState`` (Pitfall 3 recipe — no manual
    mock; tenacity sets ``outcome``/``next_action``/``fn`` itself).

    Asserts:
      (a) the planted key substring is NOT in caplog.text
      (b) the expected ``[REDACTED:<type>]`` marker IS in caplog.text
    """
    # Import inside the test body so the xfail marker swallows the
    # ImportError until Plan 14-03 lands the module.
    from docintel_core.adapters.real._logging import before_sleep_safe

    _retry_log = logging.getLogger(f"docintel.test.before_sleep_safe.{expected_marker}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(0),
        before_sleep=before_sleep_safe(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _raises_with_planted_key() -> None:
        raise ValueError(planted)

    with caplog.at_level(logging.WARNING, logger=_retry_log.name):
        with pytest.raises(ValueError):
            _raises_with_planted_key()

    # (a) raw key substring MUST be absent
    assert planted not in caplog.text, (
        f"EMP-05 / D-05: planted key substring leaked through redaction.\n"
        f"  Pattern type: {expected_marker}\n"
        f"  Planted:      {planted!r}\n"
        f"  caplog.text:  {caplog.text!r}"
    )
    # (b) expected marker MUST be present
    assert expected_marker in caplog.text, (
        f"EMP-05 / D-05: expected redaction marker absent.\n"
        f"  Expected marker: {expected_marker!r}\n"
        f"  caplog.text:     {caplog.text!r}"
    )
