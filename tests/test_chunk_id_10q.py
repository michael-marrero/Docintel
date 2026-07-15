"""Story 1.1 Task 5 — Q-keyed, PART-prefixed chunk_id (pure-function unit test).

Verifies the 10-Q chunk_id/path scheme (`{ticker}-Q{n}FY{year}-PtI-Item-2-{ord}`)
AND that the 10-K form stays byte-identical (`{ticker}-FY{year}-Item-1A-{ord}`)
so the golden 10-K corpus is unaffected by the format change (AC-4).
"""

from __future__ import annotations

from docintel_ingest.chunk import _chunk_id, _item_code_to_filename, _period_token


def test_10k_chunk_id_byte_identical() -> None:
    """Default fiscal_period keeps the pre-Story-1.1 10-K id exactly."""
    assert _chunk_id("AAPL", 2024, "Item 1A", 7) == "AAPL-FY2024-Item-1A-007"


def test_10q_part_i_chunk_id() -> None:
    assert (
        _chunk_id("AAPL", 2024, "Part I Item 2", 3, fiscal_period="Q3")
        == "AAPL-Q3FY2024-PtI-Item-2-003"
    )


def test_10q_part_ii_chunk_id() -> None:
    assert (
        _chunk_id("MSFT", 2024, "Part II Item 1A", 0, fiscal_period="Q1")
        == "MSFT-Q1FY2024-PtII-Item-1A-000"
    )


def test_part_i_and_part_ii_same_number_differ() -> None:
    a = _chunk_id("NVDA", 2024, "Part I Item 2", 0, fiscal_period="Q2")
    b = _chunk_id("NVDA", 2024, "Part II Item 2", 0, fiscal_period="Q2")
    assert a != b
    assert a == "NVDA-Q2FY2024-PtI-Item-2-000"
    assert b == "NVDA-Q2FY2024-PtII-Item-2-000"


def test_period_token() -> None:
    assert _period_token(2024, "FY") == "FY2024"
    assert _period_token(2024, "Q3") == "Q3FY2024"


def test_item_code_to_filename_10k_unchanged() -> None:
    assert _item_code_to_filename("Item 1A") == "Item-1A"
    assert _item_code_to_filename("Item 7") == "Item-7"


def test_item_code_to_filename_10q_part_abbrev() -> None:
    assert _item_code_to_filename("Part I Item 2") == "PtI-Item-2"
    assert _item_code_to_filename("Part II Item 1A") == "PtII-Item-1A"
