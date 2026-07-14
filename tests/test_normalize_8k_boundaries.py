"""Story 1.6 — 8-K flat event-item boundary detection (mechanism unit test).

Proves ``find_item_boundaries_8k`` against a synthetic 8-K-shaped string:
dotted event codes are captured, the cover/header block before the first Item
is excluded, spans stop at the next heading, and there is NO PART prefix.
The 10-K/10-Q paths are unaffected (separate regex + finder).
"""

from __future__ import annotations

from docintel_ingest.normalize import _fiscal_year_from_accession, find_item_boundaries_8k

# Synthetic 8-K: a cover/header block BEFORE the first Item, then three dotted
# event items. No PART structure (8-K is a flat item list).
_SYNTHETIC_8K = """\
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Current Report Pursuant to Section 13 or 15(d).
ITEM 2.02 Results of Operations and Financial Condition
Results prose that must be kept.
ITEM 5.02 Departure of Directors or Certain Officers
Departure prose here.
ITEM 9.01 Financial Statements and Exhibits
Exhibit list here.
"""


def _codes(text: str) -> list[str]:
    return [code for code, _, _ in find_item_boundaries_8k(text)]


def test_dotted_event_codes_captured_in_order() -> None:
    assert _codes(_SYNTHETIC_8K) == ["Item 2.02", "Item 5.02", "Item 9.01"]


def test_cover_block_before_first_item_is_excluded() -> None:
    boundaries = find_item_boundaries_8k(_SYNTHETIC_8K)
    first_start = boundaries[0][1]
    # The header text sits before the first section's char_start (not captured).
    assert _SYNTHETIC_8K[:first_start].lstrip().startswith("UNITED STATES")
    assert boundaries[0][0] == "Item 2.02"


def test_span_stops_at_next_heading() -> None:
    spans = {c: (s, e) for c, s, e in find_item_boundaries_8k(_SYNTHETIC_8K)}
    start, end = spans["Item 2.02"]
    body = _SYNTHETIC_8K[start:end]
    assert "Results prose that must be kept." in body
    assert "Departure" not in body  # stops at Item 5.02


def test_last_item_runs_to_end_of_text() -> None:
    spans = {c: (s, e) for c, s, e in find_item_boundaries_8k(_SYNTHETIC_8K)}
    _, end = spans["Item 9.01"]
    assert end == len(_SYNTHETIC_8K)


def test_no_part_prefix_on_8k_codes() -> None:
    assert all("Part" not in code for code in _codes(_SYNTHETIC_8K))


def test_empty_text_yields_no_boundaries() -> None:
    assert find_item_boundaries_8k("") == []


def test_fiscal_year_from_accession_century_pivot() -> None:
    assert _fiscal_year_from_accession("0000320193-24-000075") == 2024
    assert _fiscal_year_from_accession("0000320193-00-000001") == 2000
    assert _fiscal_year_from_accession("0000320193-98-000001") == 1998  # >=70 -> 19xx


def test_fiscal_year_from_accession_malformed_returns_none() -> None:
    # None (not a crash) so normalize_all skips the one bad file, not the whole run.
    assert _fiscal_year_from_accession("garbage") is None
    assert _fiscal_year_from_accession("0000320193-XX-000001") is None
    assert _fiscal_year_from_accession("0000320193") is None
