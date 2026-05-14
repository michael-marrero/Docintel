"""Wave 0 scaffold — IDX-02 BM25 chunk_id alignment + Pattern 4 file-layout tests.

Covers VALIDATION.md Per-Task Verification Map rows for IDX-02 (``bm25/chunk_ids.json``
length matches the BM25 row count; sidecar shape is the only reliable way to
map a retrieved row index back to a chunk_id — Pitfall 2) and Pattern 4 (bm25s
save dir produces exactly five canonical files: ``params.index.json``,
``vocab.index.json``, ``data.csc.index.npy``, ``indices.csc.index.npy``,
``indptr.csc.index.npy`` — NO ``corpus.jsonl`` because we pass ``corpus=None``).

Plan 04-04 landed ``packages/docintel-core/src/docintel_core/adapters/real/bm25s_store.py``
and Plan 04-05 wired the build pipeline; Plan 04-07 Task 1 removed the former
xfail markers so these assertions now run as hard tests.

Analog: ``tests/test_chunk_idempotency.py`` — same ``_REPO_ROOT`` constant +
read-MANIFEST-then-assert shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_chunk_ids_aligned_with_rows() -> None:
    """IDX-02: ``bm25/chunk_ids.json`` list length matches the bm25s document count.

    bm25s' ``retrieve()`` returns indices into the original corpus_tokens list
    (NOT chunk_ids). Pitfall 2 — without the sidecar, Phase 5 retrieval has no
    way to map row 47 back to ``"AAPL-FY2024-Item-1A-007"``.
    """
    bm25s = pytest.importorskip("bm25s")

    indices_root = _REPO_ROOT / "data" / "indices" / "bm25"
    chunk_ids = json.loads((indices_root / "chunk_ids.json").read_text(encoding="utf-8"))

    retriever = bm25s.BM25.load(str(indices_root))
    # bm25s 0.3.9 stores the inverted index as a CSC matrix indexed by token
    # (rows=docs, cols=vocab) on retriever.scores; the canonical document
    # count is retriever.scores["num_docs"]. The length of ``indptr - 1`` is
    # the vocab size, NOT the doc count — using it here was the original
    # Plan 04-02 scaffold bug. Plan 04-07 Task 1 corrects the extraction
    # without changing the test contract (still IDX-02 row-to-chunk_id
    # alignment) — see deviation log in 04-07-SUMMARY.md.
    num_docs = int(retriever.scores["num_docs"])

    assert len(chunk_ids) == num_docs, (
        f"bm25 chunk_ids length ({len(chunk_ids)}) != bm25s num_docs ({num_docs}) — "
        "IDX-02 row-to-chunk_id alignment broken (Pitfall 2)"
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
