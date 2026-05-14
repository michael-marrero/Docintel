"""Plan 04-04 unit tests for the two in-process store adapters.

Two adapters land in Plan 04-04 (Wave 3):

* ``Bm25sStore`` — wraps ``bm25s.BM25(method="lucene", k1=1.5, b=0.75)``;
  persists ``data/indices/bm25/{params,vocab,data.csc,indices.csc,indptr.csc}.index.*``
  + ``chunk_ids.json`` sidecar (Pitfall 2). ``commit()`` returns sha256 of the
  sorted-filename concat of the bm25s output files (Open Question #1 RESOLVED).
* ``NumpyDenseStore`` — buffers float32 vectors via ``add()``; ``commit()``
  writes ``embeddings.npy`` (plain ``np.save``, Pitfall 3) + ``chunk_ids.json``
  + returns ``sha256(embeddings.npy bytes)``. ``query()`` uses
  ``np.argpartition(-scores, k)`` then ``np.argsort`` of the top-K (CD-05).

Neither adapter is wrapped with ``@retry`` — both are in-process (no network).
The Phase 4 CI gate ``scripts/check_index_wraps.sh`` only scans for
``qdrant_client.*`` call sites, so the absence of tenacity in these two files
is correct and gate-green.

All tests in this file run in stub mode (no torch, no Qdrant) and use
``tmp_path`` so the real ``data/indices/`` tree is untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from docintel_core.adapters.protocols import BM25Store, DenseStore
from docintel_core.config import Settings
from docintel_core.types import Chunk


def _make_chunk(chunk_id: str, text: str) -> Chunk:
    """Minimal Chunk for round-trip tests."""
    return Chunk(
        chunk_id=chunk_id,
        ticker="X",
        fiscal_year=2024,
        accession="0000000000-00-000000",
        item_code="Item 1",
        item_title="Business",
        text=text,
        char_span_in_section=(0, len(text)),
        n_tokens=len(text.split()),
        prev_chunk_id=None,
        next_chunk_id=None,
        sha256_of_text=hashlib.sha256(text.encode()).hexdigest()[:16],
    )


# ---------------------------------------------------------------------------
# Bm25sStore
# ---------------------------------------------------------------------------


def test_bm25s_store_satisfies_protocol(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bm25sStore is structurally a BM25Store (D-07)."""
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.bm25s_store import Bm25sStore

    s = Bm25sStore(Settings())
    assert isinstance(s, BM25Store)
    assert s.name == "bm25s"


def test_bm25s_store_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bm25sStore.commit() then .query() returns the added chunk_ids by lexical match.

    Verifies the full add → commit → query cycle without crossing process
    boundaries (read-side disk reload covered by a separate test below).
    """
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.bm25s_store import Bm25sStore

    s = Bm25sStore(Settings())
    chunks = [
        _make_chunk("X-1", "apple banana cherry date"),
        _make_chunk("X-2", "elephant fish grape"),
        _make_chunk("X-3", "apple grape pizza"),
    ]
    s.add(chunks, [c.text for c in chunks])
    sha = s.commit()

    # Returned hash is a 64-char hex sha256 digest.
    assert isinstance(sha, str)
    assert len(sha) == 64
    int(sha, 16)  # raises if non-hex

    # bm25s save dir contains exactly the canonical files + chunk_ids.json.
    bm25_dir = tmp_path / "bm25"
    assert (bm25_dir / "params.index.json").is_file()
    assert (bm25_dir / "vocab.index.json").is_file()
    assert (bm25_dir / "data.csc.index.npy").is_file()
    assert (bm25_dir / "indices.csc.index.npy").is_file()
    assert (bm25_dir / "indptr.csc.index.npy").is_file()
    assert (bm25_dir / "chunk_ids.json").is_file()
    assert not (
        bm25_dir / "corpus.jsonl"
    ).exists(), "Pattern 4 line 392 — corpus=None on save() must suppress corpus.jsonl"

    # chunk_ids.json aligned to insertion order (Pitfall 2).
    ids = json.loads((bm25_dir / "chunk_ids.json").read_text(encoding="utf-8"))
    assert ids == ["X-1", "X-2", "X-3"]

    # Round-trip query: searching for 'apple' should return X-1 and X-3 ahead of X-2.
    results = s.query("apple", k=2)
    assert len(results) == 2
    returned_ids = {r[0] for r in results}
    assert returned_ids == {
        "X-1",
        "X-3",
    }, f"BM25 'apple' query should rank apple-bearing chunks first; got {results!r}"
    # rank is the 2nd tuple element, score is the 3rd (D-11 ranks-only).
    for chunk_id, rank, score in results:
        assert isinstance(rank, int)
        assert isinstance(score, float)


def test_bm25s_store_no_retry_decorator() -> None:
    """Bm25sStore is in-process — no tenacity wrap (D-07 implicit; SUGGESTION 11)."""
    source = Path(__file__).resolve().parent.parent / (
        "packages/docintel-core/src/docintel_core/adapters/real/bm25s_store.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "@retry" not in text, "Bm25sStore must not be retry-wrapped (in-process)"
    assert "_retry_log = logging.getLogger" not in text, (
        "Bm25sStore must not declare the SP-3 _retry_log placeholder "
        "(SUGGESTION 11 — not scanned by check_index_wraps.sh)"
    )


def test_bm25s_store_hash_is_sorted_filename_concat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Open Question #1 RESOLVED: hash covers the bm25s output files in sorted filename order.

    The sidecar chunk_ids.json is excluded from this hash (it has its own
    canonical layout and chunk content is hashed elsewhere via Chunk.sha256_of_text).
    """
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.bm25s_store import Bm25sStore

    s = Bm25sStore(Settings())
    chunks = [_make_chunk(f"X-{i}", f"token{i} alpha") for i in range(3)]
    s.add(chunks, [c.text for c in chunks])
    sha = s.commit()

    bm25_dir = tmp_path / "bm25"
    expected = hashlib.sha256()
    # Sorted by filename: the 5 .index.* files; chunk_ids.json EXCLUDED.
    for p in sorted(bm25_dir.glob("*.index.*")):
        expected.update(p.read_bytes())
    assert (
        sha == expected.hexdigest()
    ), "commit() must return sha256 of the sorted-filename concat of bm25s output files"


# ---------------------------------------------------------------------------
# NumpyDenseStore
# ---------------------------------------------------------------------------


def test_numpy_dense_store_satisfies_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """NumpyDenseStore is structurally a DenseStore (D-04)."""
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.numpy_dense import NumpyDenseStore

    s = NumpyDenseStore(Settings())
    assert isinstance(s, DenseStore)
    assert s.name == "numpy-dense-v1"


def test_numpy_dense_store_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """NumpyDenseStore.commit() then .query() returns nearest-neighbour chunk_ids first."""
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.numpy_dense import NumpyDenseStore

    s = NumpyDenseStore(Settings())
    # Three unit vectors. arr[0] = e0, arr[1] = e1, arr[2] = e0 again (almost).
    arr = np.zeros((3, 384), dtype=np.float32)
    arr[0, 0] = 1.0
    arr[1, 1] = 1.0
    arr[2, 0] = 1.0
    chunks = [_make_chunk(f"X-{i}", f"t{i}") for i in range(3)]
    s.add(chunks, arr)
    sha = s.commit()

    assert isinstance(sha, str)
    assert len(sha) == 64
    int(sha, 16)

    dense_dir = tmp_path / "dense"
    assert (dense_dir / "embeddings.npy").is_file()
    assert (dense_dir / "chunk_ids.json").is_file()

    # sha256 covers the embeddings.npy bytes verbatim (D-04, MANIFEST.dense.sha256).
    expected = hashlib.sha256((dense_dir / "embeddings.npy").read_bytes()).hexdigest()
    assert sha == expected

    # Round-trip via a fresh query vector e0 → should return X-0 / X-2 ahead of X-1.
    q = np.zeros(384, dtype=np.float32)
    q[0] = 1.0
    results = s.query(q, k=2)
    assert len(results) == 2
    top_ids = [r[0] for r in results]
    assert top_ids[0] in {"X-0", "X-2"}, f"top hit must be e0-aligned; got {top_ids!r}"
    assert top_ids[1] in {"X-0", "X-2"}, f"second hit must also be e0-aligned; got {top_ids!r}"
    for chunk_id, rank, score in results:
        assert isinstance(rank, int)
        assert isinstance(score, float)


def test_numpy_dense_store_uses_plain_np_save(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pitfall 3 — commit() must use np.save (NOT savez_compressed) for byte determinism."""
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.numpy_dense import NumpyDenseStore

    s_a = NumpyDenseStore(Settings())
    s_b = NumpyDenseStore(Settings())
    arr = np.array([[1.0, 0.0] + [0.0] * 382, [0.0, 1.0] + [0.0] * 382], dtype=np.float32)
    chunks = [_make_chunk(f"X-{i}", f"t{i}") for i in range(2)]
    s_a.add(chunks, arr)
    s_a.commit()
    a_bytes = (tmp_path / "dense" / "embeddings.npy").read_bytes()

    # Recreate the store under a different tmp dir and commit the same array →
    # byte-identical .npy bytes (Pitfall 3 canary, mirrored from
    # tests/test_index_byte_identity.py).
    tmp_b = tmp_path / "b"
    tmp_b.mkdir()
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_b))
    s_b = NumpyDenseStore(Settings())
    s_b.add(chunks, arr)
    s_b.commit()
    b_bytes = (tmp_b / "dense" / "embeddings.npy").read_bytes()

    assert a_bytes == b_bytes, (
        "NumpyDenseStore.commit() must produce byte-identical embeddings.npy across runs "
        "(Pitfall 3 — plain np.save, NOT savez_compressed)"
    )


def test_numpy_dense_store_no_retry_decorator() -> None:
    """NumpyDenseStore is in-process — no tenacity wrap (SUGGESTION 11)."""
    source = Path(__file__).resolve().parent.parent / (
        "packages/docintel-core/src/docintel_core/adapters/real/numpy_dense.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "@retry" not in text, "NumpyDenseStore must not be retry-wrapped (in-process)"
    assert "_retry_log = logging.getLogger" not in text, (
        "NumpyDenseStore must not declare the SP-3 _retry_log placeholder "
        "(SUGGESTION 11 — not scanned by check_index_wraps.sh)"
    )


def test_numpy_dense_store_uses_argpartition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CD-05 — query() uses np.argpartition for O(N) top-K (not full argsort)."""
    source = Path(__file__).resolve().parent.parent / (
        "packages/docintel-core/src/docintel_core/adapters/real/numpy_dense.py"
    )
    text = source.read_text(encoding="utf-8")
    assert (
        "argpartition" in text
    ), "CD-05 — NumpyDenseStore.query must use np.argpartition for top-K (not full argsort)"


def test_numpy_dense_store_empty_corpus_edge_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pitfall 4 (empty filings) — commit() with no chunks writes a (0, 384) array."""
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(tmp_path))
    from docintel_core.adapters.real.numpy_dense import NumpyDenseStore

    s = NumpyDenseStore(Settings())
    s.commit()  # no add()

    arr = np.load(tmp_path / "dense" / "embeddings.npy")
    assert arr.shape == (0, 384)
    assert arr.dtype == np.float32

    ids = json.loads((tmp_path / "dense" / "chunk_ids.json").read_text(encoding="utf-8"))
    assert ids == []
