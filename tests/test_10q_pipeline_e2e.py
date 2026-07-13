"""Story 1.1 — 10-Q normalize→chunk end-to-end (synthetic, offline).

Drives a hand-built 10-Q HTML through ``normalize_html(form="10-Q")`` and
``chunk_filing`` and asserts the whole 10-Q contract: PART-aware sections,
Q-keyed + PART-prefixed chunk_ids, and filing_type/fiscal_period provenance
on both the NormalizedFiling and every Chunk.

Synthetic HTML (not a committed golden) — proves the integrated pipeline
mechanism offline. The real-filing golden fixture + byte-identity re-baseline
are a separate, live-fetch-dependent step.
"""

from __future__ import annotations

import json
from pathlib import Path

from docintel_ingest.chunk import chunk_filing
from docintel_ingest.normalize import normalize_html

# Mirrors the 10-K fixture's block-heading style (<h1>ITEM ...</h1>) so text
# extraction puts each PART / ITEM heading on its own line. Part I Item 2 and
# Part II Item 2 share a number on purpose.
_SYNTHETIC_10Q_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AAPL Q3 FY2024 10-Q (fixture)</title></head>
<body>
<h1>Table of Contents</h1>
<p>Item 1. Financial Statements</p>
<p>Item 2. Management's Discussion</p>

<h1>PART I &#8212; FINANCIAL INFORMATION</h1>
<h1>ITEM 1. Financial Statements</h1>
<p>Condensed consolidated balance sheets and statements of operations for the
quarter are presented with comparative prior-period figures.</p>

<h1>ITEM 2. Management's Discussion and Analysis</h1>
<p>MANAGEMENT_DISCUSSION_SENTINEL: net sales rose in the quarter driven by
services, while gross margin expanded on a favorable product mix. This is the
Part I Item 2 body that must survive segmentation and land in its own chunk.</p>

<h1>ITEM 3. Quantitative and Qualitative Disclosures About Market Risk</h1>
<p>There have been no material changes in market risk during the quarter.</p>

<h1>ITEM 4. Controls and Procedures</h1>
<p>Disclosure controls and procedures were effective as of the end of the period.</p>

<h1>PART II &#8212; OTHER INFORMATION</h1>
<h1>ITEM 1A. Risk Factors</h1>
<p>There have been no material changes to the risk factors previously disclosed
in the annual report on Form 10-K.</p>

<h1>ITEM 2. Unregistered Sales of Equity Securities and Use of Proceeds</h1>
<p>UNREGISTERED_SALES_SENTINEL: the Company repurchased shares under its
buyback program during the quarter. This is the Part II Item 2 body and must
stay distinct from the Part I Item 2 MD&amp;A section.</p>
</body></html>
"""


def test_10q_normalize_sections_part_aware() -> None:
    nf = normalize_html(
        _SYNTHETIC_10Q_HTML,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000075",
        form="10-Q",
        fiscal_period="Q3",
    )
    assert nf.filing_type == "10-Q"
    assert nf.fiscal_period == "Q3"
    assert nf.raw_path == "data/corpus/raw/AAPL/Q3FY2024.html"

    # Part I Item 2 (MD&A) and Part II Item 2 (buybacks) are DISTINCT sections.
    assert "Part I Item 2" in nf.sections
    assert "Part II Item 2" in nf.sections
    assert "MANAGEMENT_DISCUSSION_SENTINEL" in nf.sections["Part I Item 2"]
    assert "UNREGISTERED_SALES_SENTINEL" in nf.sections["Part II Item 2"]
    # The MD&A body did NOT leak into Part II Item 2 (the merge bug).
    assert "MANAGEMENT_DISCUSSION_SENTINEL" not in nf.sections["Part II Item 2"]


def test_10q_chunk_ids_and_provenance(tmp_path: Path) -> None:
    nf = normalize_html(
        _SYNTHETIC_10Q_HTML,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000075",
        form="10-Q",
        fiscal_period="Q3",
    )
    nf_path = tmp_path / "AAPL_Q3FY2024.json"
    nf_path.write_text(nf.model_dump_json(), encoding="utf-8")

    chunks = chunk_filing(nf_path)
    assert chunks, "expected at least one chunk"

    # Every chunk carries the 10-Q provenance.
    assert all(c.filing_type == "10-Q" for c in chunks)
    assert all(c.fiscal_period == "Q3" for c in chunks)
    # Every chunk_id is Q-keyed and PART-prefixed.
    assert all(c.chunk_id.startswith("AAPL-Q3FY2024-Pt") for c in chunks)

    by_item: dict[str, list[str]] = {}
    for c in chunks:
        by_item.setdefault(c.item_code, []).append(c.chunk_id)

    # Both Item-2 sections produced chunks with DISTINCT ids.
    assert "Part I Item 2" in by_item
    assert "Part II Item 2" in by_item
    assert any(cid.startswith("AAPL-Q3FY2024-PtI-Item-2-") for cid in by_item["Part I Item 2"])
    assert any(cid.startswith("AAPL-Q3FY2024-PtII-Item-2-") for cid in by_item["Part II Item 2"])
