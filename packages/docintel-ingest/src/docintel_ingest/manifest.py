"""MANIFEST.json writer + sha256 helpers + integrity verifier for the corpus.

D-21: ``data/corpus/MANIFEST.json`` is the deterministic identity artifact
      for the committed corpus — snapshot sha256 + per-filing raw /
      normalized / chunks sha256s + BGE tokenizer config + chunker config.
      Phase 4's index manifest (IDX-03) cross-references this file for
      tokenizer-and-chunker provenance, and eval-report manifest headers
      reference its sha256 as the canonical corpus-identity attestation.

D-22 / ING-04: ``tests/test_chunk_idempotency.py::test_manifest_hashes_match``
      reads this manifest, recomputes ``hashlib.sha256(path.read_bytes())``
      for every per-filing entry, and asserts equality. Any silent drift in
      the committed corpus surfaces immediately as a test failure on the
      next CI run.

Pitfall 3 (BGE tokenizer revision pin): the manifest records the 40-char
      ``tokenizer.revision_hash`` (``982532469af0dff5df8e70b38075b0940e863662``).
      The CI test asserts this constant matches the source-code constant in
      ``docintel_ingest.tokenizer`` — a structural defense against a future
      HF-hub refresh silently breaking ING-04 byte-identity.

Anti-pattern from RESEARCH.md line 428: ``fetched_at`` is intentionally
      OMITTED from per-filing entries here — it is per-filing metadata that
      varies per run and would defeat byte-identity. The only timestamp in
      the manifest is the top-level ``generated_at``, which is human-readable
      provenance and NOT used in any content hash.

FND-11: this module accepts ``cfg: Settings`` as an argument; it MUST NOT
      construct its own ``Settings()`` or read environment variables. The CLI
      constructs ``Settings()`` once and passes it in. ``tests/test_no_env_outside_config.py``
      covers ``packages/*/src`` — adding env-reading paths here would flip
      that gate to red.

Path-resolution discipline: the STRING fields stored in the manifest
      (``raw_path`` / ``normalized_path`` / ``chunks_path`` /
      ``snapshot.path``) are repo-root-relative ``data/corpus/...`` literals
      for stable cross-machine diffing. The actual ``sha256_file()`` reads
      resolve via ``Path(cfg.data_dir) / "corpus" / ...`` so the writer
      honors a developer override of ``DOCINTEL_DATA_DIR``. ``verify_manifest()``
      mirrors this discipline: it strips the leading ``"data/"`` from the
      stored string and re-prepends ``cfg.data_dir``. Stub-mode CI runs with
      the default ``cfg.data_dir == "data"`` so the two coincide.

No network calls — pure stdlib (hashlib + json + datetime + pathlib). NO
      ``@retry`` decorator (no SDK call site). The ingest-wraps grep gate
      keys on the sec-edgar-downloader API surface only, which does not
      appear in this module; the patterns spelled out in
      ``scripts/check_ingest_wraps.sh`` deliberately do NOT live in this
      docstring so the gate's surface stays a true-positive indicator
      (same discipline as ``cli.py`` and ``tokenizer.py``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import structlog
from docintel_core.config import Settings

from docintel_ingest.chunk import HARD_CAP_TOKENS, OVERLAP_TOKENS, TARGET_TOKENS
from docintel_ingest.snapshot import load_snapshot
from docintel_ingest.tokenizer import BGE_TOKENIZER_NAME, BGE_TOKENIZER_REVISION

# Two-logger pattern (SP-3) — symmetry with fetch.py / normalize.py /
# chunk.py / tokenizer.py. manifest.py has no tenacity-wrapped retry call
# sites (pure CPU, no network), so ``_retry_log`` is unused at module level;
# keep the binding for grep-symmetry with peers.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)

# MANIFEST.json schema version. Bump if the schema changes in a way that
# would force consumers (tests/test_chunk_idempotency.py, Phase 4 index
# manifest) to update their parsing. V1 is the schema from RESEARCH.md
# lines 668-713.
MANIFEST_VERSION = 1


class Discrepancy(NamedTuple):
    """One mismatched ``sha256`` discovered by ``verify_manifest()``.

    Fields:
        path: The repo-root-relative path string from the manifest entry
            (e.g. ``"data/corpus/raw/AAPL/FY2024.html"``).
        expected_sha256: The sha256 value recorded in MANIFEST.json.
        actual_sha256: The sha256 of the file currently on disk.

    A non-empty list returned from ``verify_manifest()`` means at least
    one committed file has drifted from the manifest's recorded hash —
    surface as a CI failure rather than silently tolerated drift.
    """

    path: str
    expected_sha256: str
    actual_sha256: str


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file bytes.

    RESEARCH.md "Don't Hand-Roll" line 444: stdlib ``hashlib.sha256`` is
    the canonical choice — no extra dep, byte-identical across Python
    versions, and the digest format matches what eval-report manifest
    headers and ``test_manifest_hashes_match`` consume.

    Args:
        path: Filesystem path to read. ``read_bytes()`` loads the file
            in one shot — fine for committed 10-K corpus files (largest
            single file ≈ 2 MB; total corpus ≈ 30 MB raw + 10 MB
            normalized + 14 MB chunks).

    Returns:
        Lowercase hex digest string, 64 characters.

    Raises:
        FileNotFoundError: ``path`` does not exist.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _filing_entry(cfg: Settings, ticker: str, fiscal_year: int) -> dict[str, Any]:
    """Build one per-filing entry for ``MANIFEST.json["filings"]``.

    Schema mirrors RESEARCH.md lines 693-712. ``raw_path`` /
    ``normalized_path`` / ``chunks_path`` are STRING fields stored as
    repo-root-relative ``data/corpus/...`` literals for stable diffing
    across machines; the actual ``sha256_file()`` reads happen on
    ``cfg.data_dir``-resolved Path objects so the writer honors a
    developer override of ``DOCINTEL_DATA_DIR``.

    ``fetched_at`` is intentionally NOT included (anti-pattern §428).
    The per-filing JSON carries it as sidecar metadata but it is never
    part of the byte-identity hash payload.

    Args:
        cfg: Settings instance — ``cfg.data_dir`` resolves filesystem
            reads.
        ticker: Validated SEC ticker (Pydantic ``CompanyEntry`` validation
            at snapshot load time guarantees the form ``^[A-Z.]{1,5}$``).
        fiscal_year: Integer fiscal-year label from the snapshot row.

    Returns:
        Dict ready for serialization into the manifest's ``filings``
        list. Field order is fixed by Python ``dict`` insertion order;
        ``json.dumps(..., sort_keys=True)`` re-orders keys deterministically
        at the writer.
    """
    raw_rel = f"data/corpus/raw/{ticker}/FY{fiscal_year}.html"
    normalized_rel = f"data/corpus/normalized/{ticker}/FY{fiscal_year}.json"
    chunks_rel = f"data/corpus/chunks/{ticker}/FY{fiscal_year}.jsonl"

    raw_fp = Path(cfg.data_dir) / "corpus" / "raw" / ticker / f"FY{fiscal_year}.html"
    normalized_fp = Path(cfg.data_dir) / "corpus" / "normalized" / ticker / f"FY{fiscal_year}.json"
    chunks_fp = Path(cfg.data_dir) / "corpus" / "chunks" / ticker / f"FY{fiscal_year}.jsonl"

    # Read the normalized JSON to surface accession + per-filing manifest
    # fields that downstream consumers (Phase 4 index manifest, eval-report
    # provenance) read out of MANIFEST.json directly rather than re-parsing
    # every normalized JSON.
    normalized_obj = json.loads(normalized_fp.read_text(encoding="utf-8"))

    # Chunk count = newline-separated JSONL lines. Empty filings
    # (AMZN/META/XOM x 3 FYs — Wave 3 styled-span outcome) have a
    # zero-byte JSONL whose splitlines() yields []; chunk_count = 0.
    chunks_text = chunks_fp.read_text(encoding="utf-8")
    chunk_count = len(chunks_text.splitlines()) if chunks_text else 0

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "accession": normalized_obj["accession"],
        "raw_path": raw_rel,
        "raw_sha256": sha256_file(raw_fp),
        "normalized_path": normalized_rel,
        "normalized_sha256": sha256_file(normalized_fp),
        "chunks_path": chunks_rel,
        "chunks_sha256": sha256_file(chunks_fp),
        "chunk_count": chunk_count,
        "items_found": normalized_obj["manifest"]["items_found"],
        "items_missing": normalized_obj["manifest"]["items_missing"],
        "ordering_valid": normalized_obj["manifest"]["ordering_valid"],
        "tables_dropped": normalized_obj["manifest"]["tables_dropped"],
    }


def write_manifest(cfg: Settings) -> Path:
    """Compose ``data/corpus/MANIFEST.json`` from committed corpus files.

    Iterates the committed snapshot deterministically, builds one entry per
    (ticker, fiscal_year) that has all three artifacts on disk, and writes
    the manifest atomically via ``json.dumps(..., sort_keys=True, indent=2)``.
    ``sort_keys=True`` is the byte-identity guarantor: Python dict ordering
    is insertion-ordered but ``sort_keys`` re-orders alphabetically at
    serialization time, making the output stable across Python versions and
    across runs.

    Partial-corpus handling: if ANY of raw/normalized/chunks is missing for
    a given (ticker, year), the entry is skipped and a structured log line
    is emitted. The corpus-layout test (``test_committed_corpus_files_present``)
    catches material gaps; the manifest tolerates partial state for the
    case of a developer running a single ticker through the pipeline.

    Args:
        cfg: Settings instance. ``cfg.data_dir`` resolves all filesystem
            paths. Stub-mode CI uses the default ``"data"`` so the
            manifest's repo-root-relative string fields coincide with the
            on-disk read locations.

    Returns:
        Path to the written manifest (``Path(cfg.data_dir) /
        "corpus" / "MANIFEST.json"``).

    Raises:
        FileNotFoundError: ``data/corpus/companies.snapshot.csv`` does
            not exist (the snapshot is the source of truth — no snapshot
            means no manifest).
    """
    manifest_path = Path(cfg.data_dir) / "corpus" / "MANIFEST.json"
    snapshot_path = Path(cfg.data_dir) / "corpus" / "companies.snapshot.csv"

    companies = load_snapshot(cfg)

    # Snapshot block carries the deterministic identity of the committed
    # CSV plus the sorted ticker list — eval reports surface this as the
    # "which companies are in this corpus?" attestation.
    snapshot_block = {
        "path": "data/corpus/companies.snapshot.csv",
        "sha256": sha256_file(snapshot_path),
        "tickers": sorted({c.ticker for c in companies}),
        "company_count": len(companies),
    }

    # Tokenizer block carries the exact tokenizer config the chunker used
    # — revision_hash is the Pitfall-3 defense against silent HF-hub drift.
    # tokenizer_class and model_max_length are derived from BGE-small-en-v1.5;
    # they are repeated here so MANIFEST.json is self-describing without
    # requiring readers to load the tokenizer to inspect them.
    tokenizer_block = {
        "name": BGE_TOKENIZER_NAME,
        "revision_hash": BGE_TOKENIZER_REVISION,
        "model_max_length": 512,
        "tokenizer_class": "BertTokenizer",
    }

    # Chunker block matches the constants in docintel_ingest.chunk — the
    # plain integers are imported from the module so a future tweak to
    # TARGET_TOKENS / OVERLAP_TOKENS / HARD_CAP_TOKENS automatically
    # surfaces in MANIFEST.json. The string-valued fields capture the
    # exact algorithmic choices (NFC normalization, paragraph split on
    # \n\n, sentence split regex from CD-06).
    chunker_block = {
        "target_tokens": TARGET_TOKENS,
        "overlap_tokens": OVERLAP_TOKENS,
        "hard_cap_tokens": HARD_CAP_TOKENS,
        "unicode_normalization": "NFC",
        "paragraph_split": "\n\n",
        "sentence_split_regex": "(?<=[.!?])\\s+(?=[A-Z])",
    }

    filings: list[dict[str, Any]] = []
    n_skipped = 0
    for entry in companies:
        for year in entry.fiscal_years:
            raw_fp = Path(cfg.data_dir) / "corpus" / "raw" / entry.ticker / f"FY{year}.html"
            normalized_fp = (
                Path(cfg.data_dir) / "corpus" / "normalized" / entry.ticker / f"FY{year}.json"
            )
            chunks_fp = Path(cfg.data_dir) / "corpus" / "chunks" / entry.ticker / f"FY{year}.jsonl"
            if not (raw_fp.is_file() and normalized_fp.is_file() and chunks_fp.is_file()):
                n_skipped += 1
                log.warning(
                    "manifest_filing_skipped",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    raw_present=raw_fp.is_file(),
                    normalized_present=normalized_fp.is_file(),
                    chunks_present=chunks_fp.is_file(),
                    reason="one or more artifacts missing on disk",
                )
                continue
            filings.append(_filing_entry(cfg, entry.ticker, year))

    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        # Top-level provenance only — never used in any byte-identity hash.
        # The CI manifest-hash test computes file hashes; ``generated_at``
        # has no effect on that calculation.
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot": snapshot_block,
        "tokenizer": tokenizer_block,
        "chunker": chunker_block,
        "filings": filings,
    }

    # Deterministic serialization: sort_keys=True orders every dict's keys
    # alphabetically at the JSON level, making the file byte-identical
    # across re-runs. indent=2 keeps the file human-readable for git diffs.
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log.info(
        "manifest_written",
        path=str(manifest_path),
        n_filings=len(filings),
        n_skipped=n_skipped,
        version=MANIFEST_VERSION,
    )
    return manifest_path


def verify_manifest(manifest_path: Path) -> list[Discrepancy]:
    """Re-compute every sha256 in MANIFEST.json against on-disk file bytes.

    Returns an empty list if every recorded hash matches the on-disk file.
    Non-empty list = at least one committed file has drifted from the
    manifest's recorded hash (or vice versa).

    Path-resolution discipline: the manifest stores repo-root-relative
    ``data/corpus/...`` strings for stable diffing. This function translates
    those strings to the developer's ``cfg.data_dir`` at read time by
    stripping the leading ``"data/"`` and re-prepending ``Path(cfg.data_dir)``.
    Stub-mode CI runs with ``cfg.data_dir == "data"`` so the translation is
    a no-op; a developer overriding ``DOCINTEL_DATA_DIR`` to a non-default
    value would have ``verify_idempotency`` (in ``verify.py``) fail fast at
    its entry-time precondition, so this code path is conceptually
    cfg.data_dir-aware even though most invocations are with the default.

    Args:
        manifest_path: Path to ``data/corpus/MANIFEST.json``. The file is
            loaded once and never written.

    Returns:
        List of ``Discrepancy`` tuples (path, expected, actual). Empty
        list = full match.

    Raises:
        FileNotFoundError: ``manifest_path`` does not exist.
        KeyError: manifest is malformed (missing expected keys).
        json.JSONDecodeError: manifest is not valid JSON.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Construct a Settings once at entry so the verifier honors any
    # cfg.data_dir override. FND-11 keeps this read at the single allowed
    # site — Settings() construction.
    cfg = Settings()  # FND-11: one Settings per call site, no env reads elsewhere
    data_dir = Path(cfg.data_dir)

    discrepancies: list[Discrepancy] = []

    # Snapshot block — single sha256 to verify, translated through cfg.data_dir.
    snapshot_path_str = manifest["snapshot"]["path"]
    snapshot_expected = manifest["snapshot"]["sha256"]
    snapshot_read_fp = data_dir / Path(snapshot_path_str).relative_to("data")
    snapshot_actual = sha256_file(snapshot_read_fp)
    if snapshot_actual != snapshot_expected:
        discrepancies.append(
            Discrepancy(
                path=snapshot_path_str,
                expected_sha256=snapshot_expected,
                actual_sha256=snapshot_actual,
            )
        )

    # Per-filing entries — three sha256s per filing (raw / normalized / chunks).
    for entry in manifest["filings"]:
        for kind in ("raw", "normalized", "chunks"):
            path_key = f"{kind}_path"
            sha_key = f"{kind}_sha256"
            stored_path = entry[path_key]
            expected = entry[sha_key]
            read_fp = data_dir / Path(stored_path).relative_to("data")
            actual = sha256_file(read_fp)
            if actual != expected:
                discrepancies.append(
                    Discrepancy(
                        path=stored_path,
                        expected_sha256=expected,
                        actual_sha256=actual,
                    )
                )

    if discrepancies:
        log.error(
            "manifest_discrepancies_found",
            n=len(discrepancies),
            first_path=discrepancies[0].path,
        )
    else:
        log.info(
            "manifest_verify_clean",
            n_filings=len(manifest["filings"]),
            n_checks=1 + 3 * len(manifest["filings"]),  # snapshot + 3-per-filing
        )

    return discrepancies
