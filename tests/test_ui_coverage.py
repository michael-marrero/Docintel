"""Story 1.5 — pure coverage-view UI helpers (no Streamlit import needed)."""

from __future__ import annotations

from docintel_ui.coverage_view import scope_label, status_html, table_html, transcript_label


def test_scope_label() -> None:
    assert (
        scope_label({"company_count": 18, "fy_min": 2022, "fy_max": 2024})
        == "CORPUS · 18 FILERS · FY2022-FY2024"
    )
    # Missing span degrades gracefully.
    assert "FILERS" in scope_label({"company_count": 0, "fy_min": None, "fy_max": None})


def test_transcript_label_is_a_count_not_a_dot() -> None:
    # UX-DR19: transcript availability is a count/text label.
    assert transcript_label(9) == "9 calls"
    assert transcript_label(0) == "none"


def test_status_html_carries_the_scope_bits() -> None:
    h = status_html(
        {
            "company_count": 3,
            "forms": ["10-K", "10-Q"],
            "fy_min": 2022,
            "fy_max": 2024,
            "has_transcripts": True,
            "snapshot_date": "2026-07",
        }
    )
    assert "3</b> FILERS" in h
    assert "10-K / 10-Q" in h
    assert "EARNINGS TRANSCRIPTS" in h
    assert "FY2022&ndash;FY2024" in h


def test_table_html_shows_counts_and_transcript_label() -> None:
    rows = [
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "forms": ["10-K"],
            "filing_counts": {"10-K": 2},
            "transcript_count": 9,
            "latest_period": "FY2024",
        }
    ]
    h = table_html(rows)
    assert "AAPL" in h and "Apple Inc." in h
    assert "10-K &times;2" in h
    assert "9 calls" in h  # UX-DR19 count label, not a bare dot
    assert "FY2024" in h


def test_table_html_escapes_and_handles_unindexed() -> None:
    rows = [
        {
            "ticker": "X",
            "name": "<script>alert(1)</script>",
            "sector": "S",
            "forms": ["10-K"],
            "filing_counts": {},
            "transcript_count": 0,
            "latest_period": None,
        }
    ]
    h = table_html(rows)
    assert "<script>" not in h  # company name escaped
    assert "none" in h  # transcript label
    assert "not yet indexed" in h  # declared-but-not-indexed chip
