"""Story 1.6 — 8-K accession-keyed chunk_id + dotted-item filename (unit test).

Locks the id contract: ``{ticker}-8K-{accession_nodashes}-Item-N-N-{ord}``,
dotted item codes rendered dot->dash, and 10-K/10-Q ids byte-unchanged.
"""

from __future__ import annotations

from docintel_ingest.chunk import _chunk_id, _item_code_to_filename


def test_8k_chunk_id_is_accession_keyed_dashes_stripped() -> None:
    cid = _chunk_id(
        "AAPL", 2024, "Item 2.02", 0, filing_type="8-K", accession="0000320193-24-000075"
    )
    assert cid == "AAPL-8K-000032019324000075-Item-2-02-000"


def test_8k_dotted_item_code_to_filename() -> None:
    assert _item_code_to_filename("Item 2.02") == "Item-2-02"
    assert _item_code_to_filename("Item 9.01") == "Item-9-01"


def test_8k_ordinal_zero_padded() -> None:
    cid = _chunk_id(
        "MSFT", 2024, "Item 5.02", 12, filing_type="8-K", accession="0000789019-24-000090"
    )
    assert cid == "MSFT-8K-000078901924000090-Item-5-02-012"


def test_10k_chunk_id_byte_unchanged() -> None:
    assert _chunk_id("AAPL", 2024, "Item 1A", 7) == "AAPL-FY2024-Item-1A-007"


def test_10q_chunk_id_byte_unchanged() -> None:
    assert (
        _chunk_id("AAPL", 2024, "Part I Item 2", 3, fiscal_period="Q3")
        == "AAPL-Q3FY2024-PtI-Item-2-003"
    )
