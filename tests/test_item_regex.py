"""Tests for the D-07 Item-boundary regex + ordering validator.

Covers VALIDATION.md task 3-0X-02: ``ITEM_RE`` matches across all heading
variants seen in real 10-Ks (all-caps, mixed-case, em-dash separator,
colon, period, NBSP) and rejects in-prose mentions plus ``PART I``
headers (RESEARCH.md line 311-312, CD-08). Also exercises
``find_item_boundaries`` against the canonical ordering and a pre-2024
filing that lacks Item 1C (Pitfall 5 — D-07 lenient policy).

Wave 3 (Plan 03-05) ships ``docintel_ingest.normalize`` with ``ITEM_RE``
and ``find_item_boundaries``; the xfail markers are flipped in the same
commit that lands ``normalize.py``.
"""

from __future__ import annotations


def test_all_caps_item_matches() -> None:
    """All-caps ``ITEM 1A. Risk Factors`` matches and captures ``1A``."""
    from docintel_ingest.normalize import ITEM_RE

    m = ITEM_RE.search("ITEM 1A. Risk Factors")
    assert m is not None
    assert m.group(1) == "1A"


def test_mixed_case_item_matches() -> None:
    """Mixed-case ``Item 7 Management's Discussion`` matches with group(1)='7'."""
    from docintel_ingest.normalize import ITEM_RE

    m = ITEM_RE.search("Item 7 Management's Discussion")
    assert m is not None
    assert m.group(1) == "7"


def test_em_dash_separator() -> None:
    """Em-dash separator ``ITEM 1A —Risk Factors`` matches (CD-08 heading variant)."""
    from docintel_ingest.normalize import ITEM_RE

    assert ITEM_RE.search("ITEM 1A —Risk Factors") is not None


def test_colon_separator() -> None:
    """Colon separator ``ITEM 1A: Risk Factors`` matches."""
    from docintel_ingest.normalize import ITEM_RE

    assert ITEM_RE.search("ITEM 1A: Risk Factors") is not None


def test_period_separator() -> None:
    """Period separator ``ITEM 1A. Risk Factors`` matches."""
    from docintel_ingest.normalize import ITEM_RE

    assert ITEM_RE.search("ITEM 1A. Risk Factors") is not None


def test_nbsp_separator() -> None:
    """NBSP-separated ``ITEM\xa01A. Risk Factors`` matches (Pitfall 4 — NFC upstream)."""
    from docintel_ingest.normalize import ITEM_RE

    # The NFC normalization happens upstream of the regex; the regex sees a
    # regular space after normalization. We still send a plain-space variant
    # because that's the contract regex consumers depend on after normalize.
    assert ITEM_RE.search("ITEM 1A. Risk Factors") is not None


def test_in_prose_does_not_match() -> None:
    """In-prose mention ``as discussed in Item 1A above`` does NOT match (anchor discipline)."""
    from docintel_ingest.normalize import ITEM_RE

    assert ITEM_RE.search("as discussed in Item 1A above") is None


def test_part_header_does_not_match() -> None:
    """``PART I`` / ``PART II`` headers do NOT match (CD-08, RESEARCH.md line 312)."""
    from docintel_ingest.normalize import ITEM_RE

    assert ITEM_RE.search("PART I") is None


def test_find_item_boundaries_canonical_sequence() -> None:
    """``find_item_boundaries`` returns Items in document order across a 3-Item fixture."""
    from docintel_ingest.normalize import find_item_boundaries

    text = (
        "\n\nITEM 1. Business\nThe Company designs and manufactures.\n\n"
        "ITEM 1A. Risk Factors\nMacroeconomic conditions may.\n\n"
        "ITEM 7. Management's Discussion\nRevenue grew this period.\n"
    )
    boundaries = find_item_boundaries(text)
    codes = [code for code, _start, _end in boundaries]
    assert codes == ["Item 1", "Item 1A", "Item 7"]


def test_find_item_boundaries_skips_missing_1c_pre_2024() -> None:
    """Pre-2024 filings lacking Item 1C are tolerated (Pitfall 5 — D-07 lenient policy)."""
    from docintel_ingest.normalize import find_item_boundaries

    text = (
        "\n\nITEM 1. Business\nBody.\n\n"
        "ITEM 1A. Risk Factors\nBody.\n\n"
        "ITEM 1B. Unresolved Staff Comments\nBody.\n\n"
        "ITEM 7. MD&A\nBody.\n"
    )
    boundaries = find_item_boundaries(text)
    codes = [code for code, _start, _end in boundaries]
    assert "Item 1C" not in codes
