"""Story 1.1 Task 4 — 10-Q PART-aware boundary detection (mechanism unit test).

Proves the part-tracking LOGIC of ``find_item_boundaries_10q`` against a
synthetic 10-Q-shaped string: Part I Item 2 (MD&A) and Part II Item 2
(Unregistered Sales) stay DISTINCT, and heading matches before the first
PART header (the table-of-contents) are dropped.

This is a mechanism test, NOT a real-filing fidelity test — the golden
fixture from an actual 10-Q (heading-text variants, em-dash PART labels)
is validated later against a live fetch. The 10-K path is unaffected
(``find_item_boundaries`` untouched).
"""

from __future__ import annotations

from docintel_ingest.normalize import find_item_boundaries_10q

# Synthetic 10-Q: a ToC block listing items BEFORE any PART header, then
# PART I (Items 1–4) and PART II (Items 1A, 2) with duplicate numbers.
_SYNTHETIC_10Q = """\
Table of Contents
Item 1. Financial Statements
Item 2. Management's Discussion
PART I FINANCIAL INFORMATION
Item 1. Financial Statements
Balance sheet prose here.
Item 2. Management's Discussion and Analysis
MD&A prose that must NOT be lost.
Item 3. Quantitative and Qualitative Disclosures
Item 4. Controls and Procedures
PART II OTHER INFORMATION
Item 1A. Risk Factors
Updated risk prose.
Item 2. Unregistered Sales of Equity Securities
Buyback prose here.
"""


def _codes(text: str) -> list[str]:
    return [code for code, _, _ in find_item_boundaries_10q(text)]


def test_part_i_and_part_ii_items_stay_distinct() -> None:
    codes = _codes(_SYNTHETIC_10Q)
    assert "Part I Item 2" in codes
    assert "Part II Item 2" in codes
    # The two "Item 2" sections are NOT collapsed.
    assert codes.count("Part I Item 2") == 1
    assert codes.count("Part II Item 2") == 1


def test_toc_items_before_first_part_are_dropped() -> None:
    boundaries = find_item_boundaries_10q(_SYNTHETIC_10Q)
    # Every returned code is PART-scoped; nothing bare like "Item 1".
    assert all(code.startswith("Part ") for code, _, _ in boundaries)
    # The first real section is Part I Item 1, not a ToC entry.
    assert boundaries[0][0] == "Part I Item 1"


def test_mdna_span_carries_its_body_not_the_next_section() -> None:
    boundaries = {code: (s, e) for code, s, e in find_item_boundaries_10q(_SYNTHETIC_10Q)}
    start, end = boundaries["Part I Item 2"]
    body = _SYNTHETIC_10Q[start:end]
    assert "MD&A prose that must NOT be lost." in body
    # Span stops at the next heading — Part I Item 3 prose is excluded.
    assert "Quantitative" not in body


def test_part_ii_item_1a_present() -> None:
    assert "Part II Item 1A" in _codes(_SYNTHETIC_10Q)


def test_part_i_last_item_does_not_swallow_the_part_ii_header() -> None:
    """Part I's last item stops at the PART II header, not the next Item."""
    boundaries = {code: (s, e) for code, s, e in find_item_boundaries_10q(_SYNTHETIC_10Q)}
    start, end = boundaries["Part I Item 4"]
    body = _SYNTHETIC_10Q[start:end]
    assert "Controls and Procedures" in body  # its own heading/body kept
    assert "PART II" not in body  # the trailing PART header is NOT folded in
    assert "OTHER INFORMATION" not in body


def test_empty_text_yields_no_boundaries() -> None:
    assert find_item_boundaries_10q("") == []
