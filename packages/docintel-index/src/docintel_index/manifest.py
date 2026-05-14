"""IndexManifest composer + atomic-write + sha256 helpers + corpus identity hash.

D-13: ``data/indices/MANIFEST.json`` is the deterministic identity artifact
      for the built indices — embedder block, dense block (polymorphic by
      backend per ``IndexManifestDense``), bm25 block, corpus identity hash,
      chunk count, ISO-8601 built_at, git_sha, schema format_version. Phase
      10's eval-report manifest header (EVAL-02) imports
      ``docintel_core.types.IndexManifest`` and reads embedder/dense/bm25
      attributes through this typed contract.

Pitfall 8 / CD-08: ``_atomic_write_manifest`` writes ``MANIFEST.json.tmp``
      then ``.replace()``-s atomically. A SIGKILL mid-write leaves the OLD
      manifest intact (atomic-on-POSIX semantics). If any exception fires
      between tmp-write and rename, the ``try/finally`` cleanup unlinks the
      orphan ``.tmp`` sibling (SUGGESTION 10 — verified by Plan 04-01's
      ``test_atomic_write_partial_failure``).

Pitfall 9: ``corpus_identity_hash`` pops the ``generated_at`` key from the
      corpus MANIFEST before hashing. The corpus MANIFEST's top-level
      ``generated_at`` field is per-write provenance and varies across re-
      generations; treating it as part of the corpus identity would break
      the D-12 skip path (``index_build_skipped_unchanged_corpus``) the
      first time anyone re-ran ``docintel-ingest manifest`` on an unchanged
      corpus.

Library-version recording (Pitfall 6): the bm25 block's ``library_version``
      is sourced from ``importlib.metadata.version("bm25s")`` at build time
      and recorded in MANIFEST.json. ``tests/test_index_manifest.py::
      test_manifest_records_library_versions`` cross-checks the recorded
      value against the currently-installed bm25s version — the structural
      defense against silent file-layout drift on a dep bump.

FND-11: this module accepts ``cfg: Settings`` from build.py / verify.py /
      cli.py; it does NOT construct its own ``Settings()`` or read
      environment variables. ``tests/test_no_env_outside_config.py`` covers
      ``packages/*/src`` — adding env-reading paths here would flip that
      gate to red.

Path-resolution discipline: ``corpus_identity_hash(corpus_manifest_path)``
      reads the corpus MANIFEST from the caller-supplied Path; build.py
      resolves that path via ``Path(cfg.data_dir) / "corpus" / "MANIFEST.json"``
      so a developer override of ``DOCINTEL_DATA_DIR`` is honored.

No network calls — pure stdlib (hashlib + json + datetime + pathlib +
      importlib.metadata). The two-logger SP-3 pattern is preserved for
      grep-symmetry with peers (``_retry_log`` is unused here because
      there are no SDK call sites; structlog ``log`` is the actual logger).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NamedTuple

import structlog
from docintel_core.types import IndexManifest

# Two-logger pattern (SP-3) — _retry_log is unused at module level (no SDK
# call sites here) but the binding is preserved for grep-symmetry with peers
# (bm25s_store / numpy_dense omit this per SUGGESTION 11; manifest.py mirrors
# the ingest/manifest.py shape which DOES keep it).
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


MANIFEST_VERSION: Final[int] = 1
"""Schema version. Bump if the schema changes in a way that would force
consumers (verify.py, Phase 10's eval-report manifest header) to update their
parsing. V1 is the schema landed by Plan 04-02 in ``docintel_core.types``.
"""


class IndexDiscrepancy(NamedTuple):
    """One mismatched ``sha256`` discovered by ``verify_indices``.

    Fields:
        path: Filesystem path of the artifact whose hash drifted
            (e.g. ``"data/indices/dense/embeddings.npy"``).
        expected_sha256: The sha256 value recorded in MANIFEST.json.
        actual_sha256: The sha256 of the file currently on disk.
    """

    path: str
    expected_sha256: str
    actual_sha256: str


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file bytes.

    Mirrors ``docintel_ingest.manifest.sha256_file`` verbatim. The helper is
    duplicated rather than promoted to a shared ``docintel_core.hashing``
    module — see RESEARCH §Open Question #2 (deferred). Both helpers are
    pure stdlib and share the same algorithmic shape; a future refactor can
    promote without behavioural change.

    Args:
        path: Filesystem path to read. ``read_bytes()`` loads the file in one
            shot — fine for index artifacts (largest single file is
            ``embeddings.npy`` ~= 9 MB for a 6,053-chunk x 384-dim float32 corpus).

    Returns:
        Lowercase hex digest string, 64 characters.

    Raises:
        FileNotFoundError: ``path`` does not exist.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_identity_hash(manifest_path: Path) -> str:
    """Hash the corpus MANIFEST.json bytes with ``generated_at`` stripped (Pitfall 9).

    The corpus MANIFEST's top-level ``generated_at`` field is per-write
    provenance (ISO-8601 UTC timestamp captured at write time) and varies
    across re-generations of an otherwise-identical corpus. Hashing the file
    verbatim would break the D-12 skip path on the FIRST re-run of
    ``docintel-ingest manifest`` — even if the corpus is byte-identical.

    The fix is mechanical: load the JSON, pop the ``generated_at`` key,
    re-serialize with ``sort_keys=True / ensure_ascii=False / indent=2`` +
    trailing newline (matching the ingest writer's discipline), hash the
    UTF-8 bytes.

    Plan 04-01's ``tests/test_index_build.py::test_corpus_hash_ignores_generated_at``
    asserts that two copies of the same corpus MANIFEST that differ ONLY in
    ``generated_at`` produce the same identity hash.

    Args:
        manifest_path: Path to ``data/corpus/MANIFEST.json`` (Phase 3 D-21).

    Returns:
        Lowercase hex sha256 string, 64 characters.

    Raises:
        FileNotFoundError: ``manifest_path`` does not exist.
        json.JSONDecodeError: manifest is not valid JSON.
    """
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Strip the per-write timestamp before hashing. .pop with default=None
    # so a manifest that never had the field (defensive — older writes)
    # still hashes deterministically.
    payload.pop("generated_at", None)
    # Re-serialize with the same shape the ingest writer uses (sort_keys
    # for byte-determinism, indent=2 for human-readable diffs). ensure_ascii=False
    # matches the ingest write site — see docintel_ingest.manifest.write_manifest.
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def bm25_library_version() -> str:
    """Return the installed ``bm25s`` package version (Pitfall 6).

    Sourced from ``importlib.metadata.version("bm25s")`` at MANIFEST write
    time. Plan 04-01's ``test_manifest_records_library_versions`` cross-
    checks the recorded value against the currently-installed bm25s version
    — a future dep bump that silently shifts the file layout would surface
    as a test failure.
    """
    return importlib.metadata.version("bm25s")


def _atomic_write_manifest(path: Path, manifest: IndexManifest | dict[str, Any]) -> None:
    """Atomic MANIFEST write: tempfile + ``.replace()`` (Pitfall 8 / CD-08).

    Writes ``path.with_suffix(".json.tmp")`` with the JSON-serialised payload
    + trailing newline, then ``.replace()``-s to the destination atomically.
    ``.replace()`` is atomic on POSIX filesystems (man 2 rename); a SIGKILL
    between tmp-write and rename leaves the OLD manifest intact.

    The ``try/finally`` cleanup unlinks the orphan ``.tmp`` sibling if any
    exception fires inside the write or before the rename (SUGGESTION 10 —
    verified by Plan 04-01's ``test_atomic_write_partial_failure``). The test
    monkey-patches ``Path.replace`` to raise mid-rename and asserts both
    that the destination is unchanged AND that the ``.tmp`` file has been
    cleaned up.

    Polymorphic payload (test-contract compatibility): the helper accepts
    EITHER a full ``IndexManifest`` (the production path — build.py composes
    a schema-validated model) OR a plain ``dict`` (the test harness path —
    Plan 04-01's ``test_atomic_write_partial_failure`` passes a raw dict
    fixture). The dict branch skips Pydantic round-trip; the IndexManifest
    branch flows through ``model_dump(mode="json")`` so schema-enforced
    fields are validated at compose time and re-serialised deterministically.

    Args:
        path: Destination path (e.g. ``data/indices/MANIFEST.json``).
        manifest: Either an ``IndexManifest`` (production) or a ``dict``
            payload (test fixtures). Production callers always pass the
            typed model.

    Raises:
        Re-raises any exception from the underlying I/O (e.g. PermissionError,
        OSError on disk-full, or the ``.replace()`` failure mode).
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        # Polymorphic serialisation: dict passes through verbatim; IndexManifest
        # round-trips via model_dump(mode="json") so nested model fields are
        # dict-shaped before JSON serialisation.
        if isinstance(manifest, IndexManifest):
            payload: dict[str, Any] = manifest.model_dump(mode="json")
        else:
            payload = manifest
        # sort_keys=True makes the file byte-identical across re-runs;
        # trailing newline matches the ingest writer's discipline.
        canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        tmp_path.write_text(canonical, encoding="utf-8")
        # Atomic rename — POSIX guarantees the destination is either the OLD
        # bytes (if .replace fails) or the NEW bytes (if it succeeds); never
        # a partial write.
        tmp_path.replace(path)
    finally:
        # SUGGESTION 10: clean up the orphan .tmp file if rename never ran
        # (or partially ran). missing_ok=True is the no-op path when .replace
        # already moved the file — Path.unlink raises FileNotFoundError
        # without it, which would mask the original exception.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            # Best-effort cleanup — never raise from within finally because
            # the original exception (if any) is more informative.
            pass


def compose_manifest_built_at() -> str:
    """Return ISO-8601 UTC timestamp for the ``built_at`` MANIFEST field.

    Helper kept here so build.py's call site is symmetric with the rest of
    the manifest composition (sha256_file / corpus_identity_hash /
    bm25_library_version). The timestamp is provenance only — never used
    in any identity hash.
    """
    return datetime.now(UTC).isoformat()
