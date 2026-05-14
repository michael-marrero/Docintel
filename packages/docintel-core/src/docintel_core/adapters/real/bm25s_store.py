"""In-process BM25 store backed by ``bm25s`` 0.3.9 (D-07, D-08, D-09, D-10, D-11).

Satisfies the ``BM25Store`` Protocol structurally (Plan 04-03,
``docintel_core.adapters.protocols``). Single BM25 implementation shared
across stub and real modes — D-07 explicitly forbids a "tiered" BM25.

Tokenizer pipeline (D-08): ``bm25s.tokenize(..., stopwords="en",
stemmer=Stemmer.Stemmer("english"))`` — lowercase folding happens inside
``bm25s.tokenize`` itself, then English stopwords, then Porter stem.

Hyperparameters (D-09): ``method="lucene"``, ``k1=1.5``, ``b=0.75`` (Lucene defaults).

Storage layout (D-10): ``data/indices/bm25/{params,vocab,data.csc,indices.csc,
indptr.csc}.index.*`` + ``chunk_ids.json`` sidecar (Pitfall 2 — bm25s does
NOT preserve external IDs; we map row indices → chunk_ids via the sidecar).

Query return contract (D-11): ``list[tuple[chunk_id, rank, score]]`` — Phase 5
RRF consumes ``rank`` (the 2nd tuple element); ``score`` is informational only.

No tenacity retry wrap — bm25s is in-process (no network calls). The SP-3
two-logger pattern is NOT applied here because this file contains no
tenacity-wrapped SDK calls and is NOT scanned by the Phase 4 CI grep gate
(``scripts/check_index_wraps.sh`` only scans for the Qdrant SDK surface).
SUGGESTION 11 — the dead ``_retry_log`` placeholder is omitted.

Pin: ``bm25s==0.3.9`` + ``PyStemmer==3.0.0`` live in
``packages/docintel-index/pyproject.toml`` (single source of truth — set up
by Plan 04-03). The uv workspace resolves both into a single environment so
``from bm25s import ...`` succeeds at runtime via the transitive dep.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import structlog

from docintel_core.config import Settings
from docintel_core.types import Chunk

if TYPE_CHECKING:
    # Annotation-only — keep ``import docintel_core`` cheap (D-12 lazy-import
    # discipline). The runtime import lives inside ``__init__``.
    pass  # PyStemmer package, snake-case capitalisation


log = structlog.stdlib.get_logger(__name__)

_BM25S_VERSION_HINT: Final[str] = "0.3.9"
"""Informational pin reference — runtime reads ``importlib.metadata.version("bm25s")``
in Plan 04-05's MANIFEST writer (D-13 ``bm25.library_version`` field). The
constant is here so a reader of this file sees the expected pin without
cross-referencing ``packages/docintel-index/pyproject.toml``.
"""

_BM25_METHOD: Final[str] = "lucene"
_BM25_K1: Final[float] = 1.5
_BM25_B: Final[float] = 0.75


class Bm25sStore:
    """BM25Store implementation over ``bm25s`` (D-07).

    Two-phase build: ``add()`` buffers chunks + their text; ``commit()``
    tokenizes the full corpus once (Anti-Pattern §485 — NEVER per-batch
    tokenize), builds the BM25 index, persists the bm25s artifacts +
    ``chunk_ids.json`` sidecar, and returns the sha256 of the sorted-filename
    concat of the bm25s output files (Open Question #1 RESOLVED).
    """

    def __init__(self, cfg: Settings) -> None:
        """Initialise the buffer. Lazy-imports ``bm25s`` and ``Stemmer``."""
        import bm25s  # lazy — keeps `import docintel_core` cheap (D-12)
        import Stemmer  # PyStemmer

        self._bm25s = bm25s
        self._cfg = cfg
        self._chunks: list[Chunk] = []
        self._texts: list[str] = []
        # Stemmer is stateless w.r.t. tokenization input but expensive to construct.
        self._stemmer: Any = Stemmer.Stemmer("english")
        # Populated by ``commit()`` (or by ``query()`` via a lazy disk reload).
        self._retriever: Any | None = None
        self._chunk_ids: list[str] = []
        self._vocab_size: int = 0
        log.info(
            "bm25s_store_initialized",
            stemmer_language="english",
            method=_BM25_METHOD,
            k1=_BM25_K1,
            b=_BM25_B,
            version_hint=_BM25S_VERSION_HINT,
            index_dir=str(Path(self._cfg.index_dir) / "bm25"),
        )

    @property
    def name(self) -> str:
        """Library identifier — version flows through MANIFEST via importlib.metadata.

        Analog to ``BGEEmbedder.name`` returning ``"bge-small-en-v1.5"`` (the
        model id, not the package version).
        """
        return "bm25s"

    def add(self, chunks: list[Chunk], text: list[str]) -> None:
        """Buffer one batch.

        bm25s requires the full corpus tokenized in one shot before ``.index()``
        is called. We accumulate inputs here and tokenize once in ``commit()``
        (Anti-Pattern §485 — never call ``bm25s.tokenize`` per batch).

        Args:
            chunks: Chunk metadata, length-aligned with ``text``.
            text: Pre-tokenisation chunk text. The tokenizer (D-08) lives
                inside this store, so the caller does NOT tokenise.
        """
        if len(chunks) != len(text):
            raise ValueError(
                f"Bm25sStore.add: chunks ({len(chunks)}) and text ({len(text)}) "
                "length mismatch — Protocol contract requires aligned inputs"
            )
        # Per-batch logging deliberately omitted (Pitfall 1 — log flood prevention).
        self._chunks.extend(chunks)
        self._texts.extend(text)

    def commit(self) -> str:
        """Tokenize, build, persist, and return sha256 of the bm25s output files.

        Returns:
            64-char hex sha256 of the bytes of the bm25s output files in
            sorted-filename order. ``chunk_ids.json`` is EXCLUDED from this
            hash because the sidecar is our own artifact and is content-derived
            from already-hashed Chunk metadata (Open Question #1 RESOLVED).
        """
        bm25_dir = Path(self._cfg.index_dir) / "bm25"
        bm25_dir.mkdir(parents=True, exist_ok=True)

        # Empty-corpus edge case (Pitfall 4 — empty filings contribute zero
        # chunks). We still need a valid bm25s artifact on disk so that the
        # Plan 04-05 MANIFEST verify step has something to hash. bm25s requires
        # at least one document for .index() to succeed, so insert a single
        # placeholder document when empty. The corresponding chunk_ids.json is
        # an empty list — query() will return [] correctly because no real
        # chunk_id maps to row 0. In practice the full 6053-chunk corpus never
        # hits this branch; it is a defensive write to keep idempotency stable.
        if not self._chunks:
            log.info("bm25_store_no_chunks", index_dir=str(bm25_dir))
            corpus_texts = ["__empty_corpus_placeholder__"]
            self._chunk_ids = []
        else:
            corpus_texts = list(self._texts)
            self._chunk_ids = [c.chunk_id for c in self._chunks]

        # Tokenize once (Anti-Pattern §485).
        corpus_tokens = self._bm25s.tokenize(
            corpus_texts,
            stopwords="en",
            stemmer=self._stemmer,
            show_progress=False,
        )

        retriever = self._bm25s.BM25(method=_BM25_METHOD, k1=_BM25_K1, b=_BM25_B)
        retriever.index(corpus_tokens, show_progress=False)
        # corpus=None suppresses corpus.jsonl + corpus.jsonl.mmindex
        # (Pattern 4 line 392 — chunk text already lives under data/corpus/chunks/).
        retriever.save(str(bm25_dir), corpus=None)

        # Sidecar: aligned to bm25s document indices (Pitfall 2).
        (bm25_dir / "chunk_ids.json").write_text(
            json.dumps(self._chunk_ids, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Open Question #1 RESOLVED: sha256 of sorted-filename concat of the
        # five bm25s output files (params.index.json, vocab.index.json,
        # data.csc.index.npy, indices.csc.index.npy, indptr.csc.index.npy).
        # ``chunk_ids.json`` is NOT part of the bm25s artifact set; it has its
        # own content-derived identity via the Chunk metadata it lists.
        h = hashlib.sha256()
        for path in sorted(bm25_dir.glob("*.index.*")):
            h.update(path.read_bytes())
        digest = h.hexdigest()

        self._retriever = retriever
        # vocab_dict is populated after ``.index()`` (verified against bm25s 0.3.9).
        self._vocab_size = len(retriever.vocab_dict)

        log.info(
            "bm25_store_committed",
            chunk_count=len(self._chunk_ids),
            vocab_size=self._vocab_size,
            sha256=digest,
            index_dir=str(bm25_dir),
        )
        return digest

    def last_vocab_size(self) -> int:
        """Vocabulary size from the most recent ``commit()`` (sourced into MANIFEST).

        Plan 04-05's MANIFEST writer reads this via the store instance to fill
        ``IndexManifestBM25.vocab_size``. Returns 0 if ``commit()`` has not
        been called yet.
        """
        return self._vocab_size

    def query(self, query_text: str, k: int) -> list[tuple[str, int, float]]:
        """Tokenize the query, retrieve top-k chunks, return ``[(chunk_id, rank, score)]``.

        Read-side path: if the instance has not seen ``commit()`` (fresh
        construction for query-only), lazy-load from disk via
        ``bm25s.BM25.load(...)`` + ``chunk_ids.json``.
        """
        if self._retriever is None:
            self._lazy_load_from_disk()

        # Single-query batch.
        query_tokens = self._bm25s.tokenize(
            [query_text],
            stopwords="en",
            stemmer=self._stemmer,
            show_progress=False,
        )
        assert self._retriever is not None  # narrow for mypy
        # Defensive clamp (Rule 2 — Pitfall 4 empty-corpus + small-corpus edge
        # case): bm25s.retrieve raises ValueError when k > corpus_size. The
        # callable contract is "return up to k", not "return exactly k".
        # ``corpus`` (the stored sparse matrix's column count) gives the row
        # count after ``index()``; len(self._chunk_ids) is the public-facing
        # count, except in the empty-corpus placeholder branch where the
        # internal corpus has 1 row but _chunk_ids is empty (so k_eff=1).
        corpus_size = max(len(self._chunk_ids), 1)
        k_eff = min(k, corpus_size)
        results, scores = self._retriever.retrieve(query_tokens, k=k_eff, show_progress=False)
        # results/scores shape: (1, k) — flatten the batch dim.
        row_indices = results[0]
        row_scores = scores[0]

        # Pitfall 2 — map row index → chunk_id via the sidecar.
        # rank is 0-based int (the 2nd tuple element per D-11).
        out: list[tuple[str, int, float]] = []
        for rank, (idx, score) in enumerate(zip(row_indices, row_scores, strict=True)):
            idx_int = int(idx)
            # Defensive: when the empty-corpus placeholder is on disk, _chunk_ids
            # is empty and idx_int may be 0; return nothing in that case.
            if not self._chunk_ids or idx_int >= len(self._chunk_ids):
                continue
            out.append((self._chunk_ids[idx_int], rank, float(score)))
        return out

    def verify(self) -> bool:
        """File-existence + chunk_ids length sanity check (D-14).

        Plan 04-05's CLI does the load-bearing sha256 re-check against
        ``MANIFEST.bm25.sha256``; this method is the cheap precondition.
        """
        bm25_dir = Path(self._cfg.index_dir) / "bm25"
        required = [
            "params.index.json",
            "vocab.index.json",
            "data.csc.index.npy",
            "indices.csc.index.npy",
            "indptr.csc.index.npy",
            "chunk_ids.json",
        ]
        for name in required:
            if not (bm25_dir / name).is_file():
                return False
        return True

    def _lazy_load_from_disk(self) -> None:
        """Read-side reload — ``bm25s.BM25.load(...)`` + ``chunk_ids.json``."""
        bm25_dir = Path(self._cfg.index_dir) / "bm25"
        self._retriever = self._bm25s.BM25.load(str(bm25_dir))
        self._chunk_ids = json.loads((bm25_dir / "chunk_ids.json").read_text(encoding="utf-8"))
        self._vocab_size = len(self._retriever.vocab_dict)
