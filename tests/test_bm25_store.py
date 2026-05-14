"""Wave 0 scaffold — IDX-02 BM25 chunk_id alignment + Pattern 4 file-layout tests.

Covers VALIDATION.md Per-Task Verification Map rows for IDX-02 (``bm25/chunk_ids.json``
length matches the BM25 row count; sidecar shape is the only reliable way to
map a retrieved row index back to a chunk_id — Pitfall 2) and Pattern 4 (bm25s
save dir produces exactly five canonical files: ``params.index.json``,
``vocab.index.json``, ``data.csc.index.npy``, ``indices.csc.index.npy``,
``indptr.csc.index.npy`` — NO ``corpus.jsonl`` because we pass ``corpus=None``).

These tests are intentionally ``@pytest.mark.xfail(strict=False)`` until Plan
04-04 lands ``packages/docintel-core/src/docintel_core/adapters/real/bm25_store.py``
and Plan 04-05 wires the build pipeline. Plan 04-07 Task 1 removes the xfail
markers in the final wave gate.

Analog: ``tests/test_chunk_idempotency.py`` — same ``_REPO_ROOT`` constant +
read-MANIFEST-then-assert shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.xfail(
    strict=False,
    reason="bm25s build + sidecar chunk_ids.json land in Plan 04-04/04-05; xfail removed in Plan 04-07",
)
def test_chunk_ids_aligned_with_rows() -> None:
    """IDX-02: ``bm25/chunk_ids.json`` list length matches the bm25s row count.

    bm25s' ``retrieve()`` returns indices into the original corpus_tokens list
    (NOT chunk_ids). Pitfall 2 — without the sidecar, Phase 5 retrieval has no
    way to map row 47 back to ``"AAPL-FY2024-Item-1A-007"``.
    """
    bm25s = pytest.importorskip("bm25s")

    indices_root = _REPO_ROOT / "data" / "indices" / "bm25"
    chunk_ids = json.loads((indices_root / "chunk_ids.json").read_text(encoding="utf-8"))

    retriever = bm25s.BM25.load(str(indices_root))
    # bm25s 0.3.9 stores the CSC matrix under retriever.scores; the row count
    # is the length of the indptr - 1 (canonical scipy CSC shape).
    indptr = retriever.scores["indptr"]
    row_count = len(indptr) - 1

    assert len(chunk_ids) == row_count, (
        f"bm25 chunk_ids length ({len(chunk_ids)}) != bm25s row count ({row_count}) — "
        "IDX-02 row-to-chunk_id alignment broken (Pitfall 2)"
    )


@pytest.mark.xfail(
    strict=False,
    reason="bm25s save dir layout assertion depends on Plan 04-04/04-05 build; xfail removed in Plan 04-07",
)
def test_bm25_artifacts_present() -> None:
    """Pattern 4: bm25s save dir contains the five canonical files and NO corpus.jsonl.

    Calling ``retriever.save(dir, corpus=None)`` suppresses ``corpus.jsonl`` +
    ``corpus.jsonl.mmindex`` because chunk text already lives under
    ``data/corpus/chunks/`` — we don't duplicate it under ``data/indices/bm25/``.
    """
    indices_root = _REPO_ROOT / "data" / "indices" / "bm25"

    expected_files = [
        "params.index.json",
        "vocab.index.json",
        "data.csc.index.npy",
        "indices.csc.index.npy",
        "indptr.csc.index.npy",
    ]
    for name in expected_files:
        assert (indices_root / name).is_file(), (
            f"bm25s artifact missing: {indices_root / name} — Pattern 4 file layout"
        )

    forbidden = indices_root / "corpus.jsonl"
    assert not forbidden.exists(), (
        f"unexpected corpus.jsonl in bm25 index dir ({forbidden}) — must pass corpus=None to save() "
        "(Pattern 4 — chunk text lives under data/corpus/chunks/, not duplicated here)"
    )
