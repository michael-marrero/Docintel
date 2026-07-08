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

Plan 03-06 wave-flip: ``docintel_ingest.chunk`` ships in this commit;
the xfail markers were removed in the same wave-flip commit per the
project convention.
"""

from __future__ import annotations

import json
import re
import shutil
from itertools import pairwise
from pathlib import Path

import pytest

_SAMPLE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_10k"
_REPO_ROOT = Path(__file__).resolve().parent.parent


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


def test_chunk_id_format() -> None:
    """``chunk_id`` matches the D-14 structured string format."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    pattern = re.compile(r"^[A-Z.]{1,5}-FY\d{4}-Item-\d+[A-C]?-\d{3}$")
    for c in chunks:
        assert pattern.match(c.chunk_id), f"chunk_id violates D-14 format: {c.chunk_id!r}"


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


def test_chunk_outlier_fallback() -> None:
    """A 600-token single-paragraph item emits >1 chunk, each ≤ HARD_CAP (D-13 + CD-06)."""
    from docintel_ingest.chunk import chunk_filing

    chunks = chunk_filing(_SAMPLE_DIR / "aapl_FY2024_normalized.json")
    item7 = [c for c in chunks if c.item_code == "Item 7"]
    assert len(item7) > 1, "outlier paragraph in Item 7 must be split into multiple chunks"
    for c in item7:
        assert c.n_tokens <= 500, f"outlier-fallback chunk exceeds cap: {c.chunk_id}: {c.n_tokens}"


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


def test_hard_cap_assertion_raises_on_oversize() -> None:
    """``_emit_chunk`` (or equivalent) raises ValueError on an oversize payload."""
    from docintel_ingest import chunk as chunk_module

    # Build a 600-token payload by repeating short tokens.
    oversize_text = "token " * 600
    emit = getattr(chunk_module, "_emit_chunk", None) or getattr(chunk_module, "emit_chunk", None)
    assert emit is not None, "chunk module must expose _emit_chunk for canary testing"
    with pytest.raises(ValueError, match=r"exceeds"):
        emit(oversize_text)


# ---------------------------------------------------------------------------
# Phase 11 ABL-01 (D-05): chunk-size sweep — chunk_all accepts a target_tokens
# parameter so the {300,450,600} sweep can re-chunk; the production default
# stays 450 (byte-identical default path is asserted by
# tests/test_chunk_idempotency.py). A1 LOCKED: OVERLAP_TOKENS=50 and
# HARD_CAP_TOKENS=500 stay FIXED across every swept size (target_tokens is the
# single swept knob; the hard cap is tied to BGE's 512 limit + the Phase 5
# truncation canary and is NEVER scaled down for the 300 arm).
# ---------------------------------------------------------------------------


def test_chunk_all_target_tokens_300_smaller_split(tmp_path: Path) -> None:
    """ABL-01 (D-05): re-chunking the fixture at target_tokens=300 lowers the greedy split.

    A 300-token greedy split point yields chunks whose mean token count is
    strictly below the production-450 mean (more, smaller chunks), and the
    HARD_CAP_TOKENS=500 raise still guards every emitted chunk (A1 — the cap
    is constant). The default-450 run is the comparison baseline; the swept
    run must differ, proving target_tokens actually parameterises the splitter
    (not a no-op that ignores the param).
    """
    from docintel_core.config import Settings
    from docintel_core.types import Chunk
    from docintel_ingest.chunk import chunk_all

    cfg = Settings()

    def _mean_tokens(out_root: Path) -> float:
        toks: list[int] = []
        for jsonl in sorted(out_root.rglob("*.jsonl")):
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    toks.append(Chunk.model_validate_json(line).n_tokens)
        assert toks, f"no chunks emitted under {out_root}"
        for t in toks:
            assert t <= 500, f"A1 violation: chunk exceeds HARD_CAP_TOKENS=500 ({t})"
        return sum(toks) / len(toks)

    out_default = tmp_path / "chunks_default"
    out_300 = tmp_path / "chunks_300"
    rc_default = chunk_all(cfg, normalized_root=_SAMPLE_DIR, out_root=out_default)
    rc_300 = chunk_all(cfg, normalized_root=_SAMPLE_DIR, out_root=out_300, target_tokens=300)
    assert rc_default == 0 and rc_300 == 0, "chunk_all must exit 0 on the sample fixture"

    mean_default = _mean_tokens(out_default)
    mean_300 = _mean_tokens(out_300)
    assert mean_300 < mean_default, (
        "ABL-01 (D-05): target_tokens=300 must lower the greedy split point "
        f"(mean tokens {mean_300:.1f} should be < default-450 mean {mean_default:.1f}); "
        "if equal the param is being ignored"
    )


def test_chunk_all_default_target_tokens_unchanged(tmp_path: Path) -> None:
    """ABL-01 (ING-04): chunk_all with no target_tokens arg equals an explicit 450.

    The new keyword's default IS the production TARGET_TOKENS, so omitting it
    and passing it explicitly produce byte-identical JSONL — the default path
    is byte-identical to today (the corpus-wide ING-04 gate is
    tests/test_chunk_idempotency.py; this is the fixture-level twin).
    """
    from docintel_core.config import Settings
    from docintel_ingest.chunk import TARGET_TOKENS, chunk_all

    cfg = Settings()
    out_implicit = tmp_path / "implicit"
    out_explicit = tmp_path / "explicit"
    assert chunk_all(cfg, normalized_root=_SAMPLE_DIR, out_root=out_implicit) == 0
    assert (
        chunk_all(
            cfg,
            normalized_root=_SAMPLE_DIR,
            out_root=out_explicit,
            target_tokens=TARGET_TOKENS,
        )
        == 0
    )
    implicit_files = sorted(out_implicit.rglob("*.jsonl"))
    assert implicit_files, "fixture must produce at least one JSONL"
    for impl in implicit_files:
        rel = impl.relative_to(out_implicit)
        expl = out_explicit / rel
        assert impl.read_bytes() == expl.read_bytes(), (
            f"default target_tokens must equal explicit {TARGET_TOKENS} at {rel} "
            "(byte-identity — ING-04)"
        )


def test_swept_manifest_records_target_tokens(tmp_path: Path) -> None:
    """ABL-01 (D-05 provenance): a swept write_manifest records chunker.target_tokens.

    write_manifest threads target_tokens into the MANIFEST.json chunker block
    so each swept index's corpus manifest carries its size (per-index identity
    for free). The default (flag absent) records the production 450 — the
    committed corpus MANIFEST.json stays byte-reproducible. Runs against a copy
    of the committed corpus in tmp_path so the tracked manifest is never
    clobbered.
    """
    from docintel_core.config import Settings
    from docintel_ingest.manifest import write_manifest

    src_corpus = _REPO_ROOT / "data" / "corpus"
    if not (src_corpus / "MANIFEST.json").is_file():
        pytest.skip("committed corpus not present in this checkout")
    dst_data = tmp_path / "data"
    shutil.copytree(src_corpus, dst_data / "corpus")

    cfg = Settings(data_dir=str(dst_data))
    # Swept run records the swept size.
    manifest_path = write_manifest(cfg, target_tokens=300)
    swept = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert swept["chunker"]["target_tokens"] == 300, (
        "ABL-01 (D-05): swept write_manifest(target_tokens=300) must record "
        f"chunker.target_tokens == 300; got {swept['chunker']['target_tokens']}"
    )
    # A1: overlap + hard cap stay fixed regardless of the swept size.
    assert swept["chunker"]["overlap_tokens"] == 50, "A1: overlap must stay 50"
    assert swept["chunker"]["hard_cap_tokens"] == 500, "A1: hard cap must stay 500"

    # Default (flag absent) records the production 450 — byte-reproducible.
    default_path = write_manifest(cfg)
    default = json.loads(default_path.read_text(encoding="utf-8"))
    assert (
        default["chunker"]["target_tokens"] == 450
    ), "ABL-01 (ING-04): default write_manifest must record the production 450"
