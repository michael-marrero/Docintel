"""Idempotency verifier — re-chunk committed normalized JSON; assert byte-identity.

D-22 / ING-04 headline acceptance gate: re-running the chunker on the
committed ``data/corpus/normalized/**`` JSONs must produce byte-identical
output vs. the committed ``data/corpus/chunks/**`` JSONLs. The CI test
``tests/test_chunk_idempotency.py::test_chunks_byte_identical`` exercises
this contract via the CLI; ``verify_idempotency()`` is the same contract
exposed as a library call for the CLI ``verify`` subcommand and for any
future eval-harness preflight check.

This verifier does NOT re-fetch (no network) and does NOT re-normalize
(no selectolax). It ONLY re-chunks. The point is to guarantee that the
chunker is deterministic: same normalized JSON in, same chunk JSONL out.
Re-fetching is impractical in CI (no live sec.gov call), and re-normalizing
adds a third moving part to the byte-identity contract that doesn't earn
its keep — the chunker is by far the most algorithm-heavy step and the
one most likely to drift across refactors.

The companion ``verify_manifest()`` (in ``docintel_ingest.manifest``)
catches a different failure mode: drift between MANIFEST.json's recorded
sha256s and the actual committed file bytes. ``verify_idempotency()``
catches drift in the chunker itself (the algorithm); ``verify_manifest()``
catches drift in the committed corpus (the data). Both run as part of
``docintel-ingest verify`` for defense in depth.

Anti-pattern from RESEARCH.md line 428 / Pitfall 3 reference: the byte-
identity contract excludes ``fetched_at`` (per-filing metadata that varies
per run). The chunker reads ``fetched_at`` from the normalized JSON only
for provenance — it does NOT include it in any chunk text or
``sha256_of_text``. Re-runs of the chunker against the same normalized
JSON therefore produce byte-identical JSONL, regardless of when the
normalized JSON was fetched.

FND-11: ``cfg: Settings`` passed in; this module does NOT read environment
variables or construct its own ``Settings()``. The CLI dispatcher
constructs ``Settings()`` once in ``main()`` and passes it through.

No network calls — pure CPU. The ingest-wraps grep gate keys on the
sec-edgar-downloader API surface only, which does not appear in this
module; the patterns spelled out in ``scripts/check_ingest_wraps.sh``
deliberately do NOT live in this docstring so the gate's surface stays
a true-positive indicator (same discipline as ``cli.py``, ``tokenizer.py``,
and ``manifest.py``).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import structlog
from docintel_core.config import Settings

from docintel_ingest.chunk import chunk_all
from docintel_ingest.manifest import sha256_file, verify_manifest

# Two-logger pattern (SP-3) — symmetry with fetch.py / normalize.py /
# chunk.py / tokenizer.py / manifest.py. verify.py has no tenacity-wrapped
# retry call sites (pure CPU, no network), so ``_retry_log`` is unused at
# module level; keep the binding for grep-symmetry with peers.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


def verify_idempotency(cfg: Settings) -> int:
    """Re-chunk committed normalized JSON; assert byte-identity vs. committed JSONL.

    This is the headline ING-04 / D-22 acceptance gate exposed as a library
    function. The same contract is exercised end-to-end via the CLI by
    ``tests/test_chunk_idempotency.py::test_chunks_byte_identical``; this
    function is the call path for the ``docintel-ingest verify`` subcommand
    and any future eval-harness preflight check.

    Steps:
        1. Create a ``tempfile.TemporaryDirectory()`` for re-chunked output.
        2. Re-run ``chunk_all(cfg, normalized_root=..., out_root=tmp)`` over
           the committed normalized JSONs.
        3. For every committed ``data/corpus/chunks/**/*.jsonl`` file,
           compute ``sha256_file(committed_path)`` and
           ``sha256_file(tmp_path / committed.relative_to(committed_root))``.
           Mismatch = chunker drift; log and accumulate.
        4. Call ``verify_manifest(MANIFEST.json)`` for the orthogonal
           data-drift check.
        5. Log a structured summary.
        6. Return 0 if both check sets are clean; 1 otherwise.

    Precondition: ``cfg.data_dir == "data"`` is asserted at entry. The
    manifest stores repo-root-relative ``data/corpus/...`` strings, so a
    developer overriding ``DOCINTEL_DATA_DIR`` to a non-default value would
    have ``verify_manifest`` produce false mismatches (manifest reads
    succeed against the override location, but the stored sha256s were
    computed at write time against THAT override — round-trip works for
    write-then-verify but a verification run against a manifest produced
    in a different ``data_dir`` would erroneously flag everything).
    Fail fast here with an actionable message rather than emitting a wall
    of spurious mismatches downstream.

    Args:
        cfg: Settings instance — ``cfg.data_dir`` resolves all on-disk
            paths.

    Returns:
        Shell exit code:
            * 0 — every committed JSONL matches its re-chunked counterpart
              AND every manifest sha256 matches the on-disk file.
            * 1 — at least one byte-identity violation OR manifest
              discrepancy detected (each is logged before return).

    Raises:
        AssertionError: ``cfg.data_dir != "data"`` (CI's stub-mode default).
    """
    assert cfg.data_dir == "data", (
        f"verify_idempotency requires cfg.data_dir == 'data' (the default) but "
        f"got {cfg.data_dir!r}. MANIFEST.json stores repo-root-relative paths; "
        "a non-default DOCINTEL_DATA_DIR breaks the cross-machine byte-identity "
        "contract. Unset DOCINTEL_DATA_DIR before running `docintel-ingest verify`."
    )

    committed_root = Path(cfg.data_dir) / "corpus" / "chunks"
    normalized_root = Path(cfg.data_dir) / "corpus" / "normalized"
    manifest_path = Path(cfg.data_dir) / "corpus" / "MANIFEST.json"

    n_files_checked = 0
    mismatches: list[tuple[str, str, str]] = []  # (rel_path, committed_sha, tmp_sha)

    with tempfile.TemporaryDirectory(prefix="docintel-verify-") as tmpdir:
        tmp_chunks = Path(tmpdir) / "chunks"
        log.info(
            "verify_idempotency_chunking",
            normalized_root=str(normalized_root),
            out_root=str(tmp_chunks),
        )
        rc = chunk_all(cfg, normalized_root=normalized_root, out_root=tmp_chunks)
        if rc != 0:
            log.error("verify_chunk_step_failed", rc=rc)
            return 1

        # Re-walk the committed chunks tree; for each committed file compute
        # sha256 of both the committed bytes and the re-chunked bytes and
        # compare. Zero-byte JSONLs (Wave 3 styled-span outcome — AMZN/META/
        # XOM x 3 FYs) are handled identically: sha256 of zero bytes is
        # e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855,
        # which the chunker also produces for empty normalized sections.
        committed_files = sorted(committed_root.rglob("*.jsonl"))
        for committed in committed_files:
            rel = committed.relative_to(committed_root)
            rerun_path = tmp_chunks / rel
            if not rerun_path.is_file():
                # Should not happen — chunk_all writes exactly one JSONL
                # per normalized JSON. Surface this as a mismatch so the
                # tester can investigate (probably a normalized JSON was
                # removed between waves).
                mismatches.append((str(rel), "<committed-exists>", "<rerun-missing>"))
                continue
            committed_sha = sha256_file(committed)
            rerun_sha = sha256_file(rerun_path)
            n_files_checked += 1
            if committed_sha != rerun_sha:
                log.error(
                    "idempotency_mismatch",
                    path=str(rel),
                    committed_sha256=committed_sha,
                    rerun_sha256=rerun_sha,
                )
                mismatches.append((str(rel), committed_sha, rerun_sha))

    # Orthogonal data-drift check via MANIFEST.json.
    discrepancies = verify_manifest(manifest_path)

    log.info(
        "idempotency_check_complete",
        n_files_checked=n_files_checked,
        n_mismatches=len(mismatches),
        manifest_discrepancies=len(discrepancies),
    )

    if mismatches or discrepancies:
        log.error(
            "idempotency_failed",
            n_chunk_mismatches=len(mismatches),
            n_manifest_discrepancies=len(discrepancies),
        )
        return 1

    return 0
