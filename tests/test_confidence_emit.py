"""Plan 07-01 Wave 0 xfail scaffolds for D-04 confidence emit mechanics.

Covers VALIDATION.md rows for D-04 (SYNTHESIS_PROMPT confidence instruction +
parse_confidence helper + hash rotation):

* test_parse_confidence — parse_confidence("...text.\n[confidence: high]")
  returns ("...text.", "high"); marker absent from stripped text.
* test_parse_confidence_missing — no marker → (text, None); caller falls
  back to "medium".
* test_synthesis_hash_rotated — after the Wave 2 SYNTHESIS_PROMPT edit,
  _SYNTHESIS_HASH != "dab1bcf7379f" and PROMPT_VERSION_HASH != "dab1bcf7379f"
  (the old Phase 6 combined hash). The test asserts inequality with the old
  value only — does NOT hardcode the new expected hash (which is re-derived
  at import time from the edited SYNTHESIS_PROMPT body).

All three tests are xfail-strict-marked because parse_confidence does not
yet exist in docintel_generate.parse at Wave 0, and SYNTHESIS_PROMPT has
not yet been edited (the hash rotation happens in Wave 2). The in-function
imports raise ImportError or the hash assertion fails → pytest counts these
as expected failures under xfail(strict=True). Plans 07-02 (parse_confidence)
and 07-03 (SYNTHESIS_PROMPT edit) flip these xfails to passing.

Analogs:
* ``tests/test_prompt_version_hash.py`` (full file, 112 lines) —
  exact structural analog: file header, in-function imports, hash format
  and round-trip assertion patterns. NO test hardcodes the old hash value.
* 07-PATTERNS.md §"tests/test_confidence_emit.py" — parse_confidence
  extraction test, round-trip + missing marker test, hash rotation test.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(
    strict=True,
    reason="Phase 7 Wave 1/2: from_generation_result / parse_confidence not yet defined",
)

# Old Phase 6 combined PROMPT_VERSION_HASH value (pre-Phase-7 SYNTHESIS_PROMPT edit).
# After Plan 07-03 edits SYNTHESIS_PROMPT to add the confidence instruction,
# _SYNTHESIS_HASH rotates, cascading to PROMPT_VERSION_HASH.
# No new hash value is hardcoded here — test asserts inequality with the old value only.
_OLD_COMBINED_HASH = "dab1bcf7379f"
_OLD_SYNTHESIS_HASH = "ec466290503d"


def test_parse_confidence() -> None:
    """D-04 + Pattern 3 — parse_confidence extracts marker and strips it from text.

    parse_confidence("Some answer text.\n[confidence: high]") must return
    ("Some answer text.", "high"). The stripped text must not contain
    "[confidence:" (Pitfall 6 guard — Answer.text must be clean for the UI).
    """
    from docintel_generate.parse import parse_confidence

    stripped, conf = parse_confidence("Some answer text.\n[confidence: high]")
    assert conf == "high", (
        f"D-04: parse_confidence must extract 'high'; got conf={conf!r}"
    )
    assert "[confidence:" not in stripped, (
        f"D-04: stripped text must not contain the marker; got stripped={stripped!r}"
    )
    assert stripped.endswith("text."), (
        f"D-04: stripped text must end with 'text.' (rstripped); got {stripped!r}"
    )


def test_parse_confidence_missing() -> None:
    """D-04 — no marker present → (text, None); from_generation_result falls back to "medium".

    When SYNTHESIS_PROMPT fails to elicit a confidence marker (e.g. for
    very short stub responses), parse_confidence must return (original_text,
    None) without raising. The caller uses "medium" as the default (D-03).
    """
    from docintel_generate.parse import parse_confidence

    text = "Some answer with no marker."
    stripped, conf = parse_confidence(text)
    assert conf is None, (
        f"D-04: parse_confidence with no marker must return conf=None; got {conf!r}"
    )
    assert stripped == text, (
        f"D-04: stripped text must equal original when no marker; got {stripped!r}"
    )


def test_synthesis_hash_rotated() -> None:
    """D-04 — after SYNTHESIS_PROMPT edit, _SYNTHESIS_HASH != old value + PROMPT_VERSION_HASH != old value.

    Plan 07-03 appends the confidence instruction to SYNTHESIS_PROMPT.
    The _h(SYNTHESIS_PROMPT) hash must rotate away from the Phase 6 value
    "ec466290503d", which cascades to PROMPT_VERSION_HASH (was "dab1bcf7379f").

    This test DOES NOT hardcode the new expected hash — it asserts only
    that the old value is no longer current. The new hash is re-derived
    at import time from the edited SYNTHESIS_PROMPT body (no manual update).
    See RESEARCH.md Focus Q2 for the safe re-derivation procedure.
    """
    from docintel_generate.prompts import PROMPT_VERSION_HASH, _SYNTHESIS_HASH

    assert _SYNTHESIS_HASH != _OLD_SYNTHESIS_HASH, (
        f"D-04: _SYNTHESIS_HASH must rotate after SYNTHESIS_PROMPT edit; "
        f"still equals old value {_OLD_SYNTHESIS_HASH!r} — SYNTHESIS_PROMPT "
        f"may not have been edited yet"
    )
    assert PROMPT_VERSION_HASH != _OLD_COMBINED_HASH, (
        f"D-04: PROMPT_VERSION_HASH must rotate after SYNTHESIS_PROMPT edit; "
        f"still equals old value {_OLD_COMBINED_HASH!r}"
    )
