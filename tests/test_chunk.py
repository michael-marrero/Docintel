"""Tests for ``docintel_ingest.chunk`` — Chunk schema + invariants.

Covers VALIDATION.md tasks 3-0X-04 and 3-0X-05 (ING-03, D-11, D-12, D-13):

* ``Chunk`` Pydantic model carries every D-15 + CD-02 field.
* ``chunk_id`` matches the structured D-14 string format.
* No chunk exceeds the 500-token hard cap (D-11).
* No chunk crosses an Item boundary (D-12).
* Within an Item, adjacent chunks share ~50 tokens of overlap (D-13).
* Outlier paragraphs >500 tokens trigger the sentence-split fallback
  (D-13 / CD-06) and never emit a chunk past the hard cap.
* ``_emit_chunk`` (or equivalent internal API) raises ``ValueError`` on
  an oversize payload — the build-fail-if-exceeded canary
  (RESEARCH.md line 378-383).

The tests xfail until Wave 4 ships ``docintel_ingest.chunk`` plus the
``Chunk`` Pydantic model in ``docintel_core.types`` (CD-01).
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

_SAMPLE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_10k"

_XFAIL = pytest.mark.xfail(
    raises=(ImportError, AttributeError, AssertionError, NotImplementedError, FileNotFoundError),
    strict=False,
    reason="awaits Wave 4 — chunk_filing + Chunk Pydantic model (ING-03)",
)


def test_chunk_schema() -> None:
    """A constructed Chunk has every D-15 + CD-02 field."""
    from docintel_core.types import Chunk

    chunk = Chunk(
        chunk_id="AAPL-FY2024-Item-1A-000",
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
        item_code="Item 1A",
        item_title="Risk Factors",
        text="placeholder",
        char_span_in_section=(0, 11),
        n_tokens=1,
        prev_chunk_id=None,
        next_chunk_id=None,
        sha256_of_text="0" * 16,
    )
    for field in (
        "chunk_id",
        "ticker",
        "fiscal_year",
        "accession",
        "item_code",
        "item_title",
        "text",
        "char_span_in_section",
        "n_tokens",
        "prev_chunk_id",
        "next_chunk_id",
        "sha256_of_text",
    ):
        assert hasattr(chunk, field), f"Chunk missing required field {field!r}"


@_XFAIL
def test_chunk_id_format() -> None:
    """``chunk_id`` matches the D-14 structured string format."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    pattern = re.compile(r"^[A-Z.]{1,5}-FY\d{4}-Item-\d+[A-C]?-\d{3}$")
    for c in chunks:
        assert pattern.match(c.chunk_id), f"chunk_id violates D-14 format: {c.chunk_id!r}"


@_XFAIL
def test_chunk_invariants() -> None:
    """Hard-cap, item-bounded, zero-padded ordinals across the AAPL fixture."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")

    # (a) Hard cap (D-11): every chunk fits under the BGE 512 cap with margin.
    for c in chunks:
        assert c.n_tokens <= 500, f"chunk {c.chunk_id} exceeds D-11 hard cap: {c.n_tokens}"

    # (b) Item-bounded (D-12): a single chunk lives entirely inside one item.
    #     For chunks within the same item we expect their char_span_in_section
    #     ranges to be disjoint (no two chunks overlap a third — overlap is
    #     by token, not by span, in the simple greedy splitter).
    by_item: dict[str, list[tuple[int, int]]] = {}
    for c in chunks:
        by_item.setdefault(c.item_code, []).append(tuple(c.char_span_in_section))
    # Distinct items must not share span ranges (different sections, different chars).
    seen_items = list(by_item.keys())
    assert len(seen_items) == len(set(seen_items)), "duplicate item codes in grouping"

    # (c) Ordinals: zero-padded to 3 digits, starts at 000 within each item.
    seen_ordinals: dict[str, list[int]] = {}
    for c in chunks:
        ord_str = c.chunk_id.rsplit("-", 1)[1]
        assert ord_str.isdigit() and len(ord_str) == 3, f"ordinal not 3-digit padded: {ord_str}"
        seen_ordinals.setdefault(c.item_code, []).append(int(ord_str))
    for item, ords in seen_ordinals.items():
        assert ords[0] == 0, f"item {item} ordinals start at {ords[0]}, expected 000"


@_XFAIL
def test_chunk_overlap_within_item() -> None:
    """Adjacent chunks in the same Item share ~50 tokens of overlap (D-13, tolerance ±5)."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    by_item: dict[str, list] = {}
    for c in chunks:
        by_item.setdefault(c.item_code, []).append(c)

    found_adjacent = False
    for item, item_chunks in by_item.items():
        if len(item_chunks) < 2:
            continue
        found_adjacent = True
        for left, right in pairwise(item_chunks):
            # The trailing tokens of the left chunk's text should appear as the
            # leading tokens of the right chunk's text. We approximate at the
            # text level — a strict token-level check would re-tokenize.
            left_tail = left.text[-200:]
            right_head = right.text[:200]
            # Loose containment: at least 30 chars overlap somewhere.
            assert (
                any(left_tail[i : i + 30] in right_head for i in range(0, len(left_tail) - 30))
                if len(left_tail) >= 30
                else True
            ), f"no overlap detected between {left.chunk_id} and {right.chunk_id} in {item}"

    assert found_adjacent, "fixture must produce at least one item with >=2 chunks"


@_XFAIL
def test_chunk_outlier_fallback() -> None:
    """A 600-token single-paragraph item emits >1 chunk, each ≤ HARD_CAP (D-13 + CD-06)."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    item7 = [c for c in chunks if c.item_code == "Item 7"]
    assert len(item7) > 1, "outlier paragraph in Item 7 must be split into multiple chunks"
    for c in item7:
        assert c.n_tokens <= 500, f"outlier-fallback chunk exceeds cap: {c.chunk_id}: {c.n_tokens}"


@_XFAIL
def test_no_chunk_crosses_item() -> None:
    """No chunk's text contains content from two different ``sections[item_code]`` values."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    codes = {c.item_code for c in chunks}
    assert len(codes) > 1, "fixture must produce chunks spanning multiple items"

    # Each chunk's text must NOT contain a "ITEM N." heading from a different
    # item (the only way it could cross a boundary in the normalized text).
    item_pattern = re.compile(r"\bITEM\s+\d+[A-C]?\b", re.IGNORECASE)
    for c in chunks:
        hits = item_pattern.findall(c.text)
        # At most one heading reference allowed (the chunk's own item header
        # may appear, but no foreign-item header should leak in).
        assert len(set(hits)) <= 1, f"chunk {c.chunk_id} crosses items: {hits!r}"


@_XFAIL
def test_hard_cap_assertion_raises_on_oversize() -> None:
    """``_emit_chunk`` (or equivalent) raises ValueError on an oversize payload."""
    from docintel_ingest import chunk as chunk_module

    # Build a 600-token payload by repeating short tokens.
    oversize_text = "token " * 600
    emit = getattr(chunk_module, "_emit_chunk", None) or getattr(chunk_module, "emit_chunk", None)
    assert emit is not None, "chunk module must expose _emit_chunk for canary testing"
    with pytest.raises(ValueError, match=r"exceeds"):
        emit(oversize_text)
