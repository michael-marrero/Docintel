"""Story 1.1 Task 2 — 10-Q fetch dispatch: quarter extraction (offline unit).

The live fetch path (``fetch_all`` → sec.gov) is exercised by ``@pytest.mark.real``
integration runs. This covers the pure, offline-verifiable piece: extracting the
quarter from the raw iXBRL ``dei:DocumentFiscalPeriodFocus`` cover-page tag —
validated against a live AAPL 10-Q (Q2 FY2026) during development.
"""

from __future__ import annotations

import pytest

from docintel_ingest.fetch import _extract_fiscal_period

# Shapes seen in real inline-XBRL primary documents.
_IX = '<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="c">{v}</ix:nonNumeric>'


@pytest.mark.parametrize("q", ["Q1", "Q2", "Q3"])
def test_extracts_quarter(q: str) -> None:
    assert _extract_fiscal_period(_IX.format(v=q)) == q


def test_extracts_quarter_with_whitespace() -> None:
    assert _extract_fiscal_period('name="dei:DocumentFiscalPeriodFocus">  Q3  <') == "Q3"


def test_case_insensitive_tag() -> None:
    assert _extract_fiscal_period('name="DEI:DocumentFiscalPeriodFocus">Q1<') == "Q1"


def test_fy_annual_marker() -> None:
    assert _extract_fiscal_period(_IX.format(v="FY")) == "FY"


def test_missing_tag_returns_none() -> None:
    assert _extract_fiscal_period("<html><body>no dei tags</body></html>") is None


def test_ignores_unrelated_dei_tags() -> None:
    html = '<span name="dei:DocumentType">10-Q</span><span name="dei:EntityRegistrantName">X</span>'
    assert _extract_fiscal_period(html) is None
