"""Tests for ING-04 byte-identity — the headline Phase 3 acceptance gate.

Covers VALIDATION.md tasks 3-0X-06 and 3-0X-07 (ING-04, D-21, D-22):

* Re-running ``docintel-ingest chunk`` against the committed normalized
  JSON produces byte-identical JSONL files vs. the committed
  ``data/corpus/chunks/**``.
* Every per-filing sha256 in ``data/corpus/MANIFEST.json`` matches
  ``hashlib.sha256(path.read_bytes()).hexdigest()`` for the actual
  raw / normalized / chunks files. The tokenizer revision pin
  (Pitfall 3 — ``982532469af0dff5df8e70b38075b0940e863662``) is also
  asserted to prevent silent BGE drift.

Both tests went GREEN with Plan 03-07 — ``docintel_ingest.manifest``
landed ``data/corpus/MANIFEST.json`` + ``docintel_ingest.verify`` wired
the idempotency contract through the CLI. Re-running these in CI on
every push is the cheap-and-loud defense against silent corpus drift.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_chunks_byte_identical(tmp_path: Path) -> None:
    """Re-running the chunker on committed normalized JSON yields byte-identical JSONL files."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "docintel-ingest",
            "chunk",
            "--normalized-root",
            "data/corpus/normalized",
            "--out-root",
            str(tmp_path / "chunks"),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"docintel-ingest chunk exited {result.returncode}: stderr={result.stderr!r}"

    committed_root = _REPO_ROOT / "data" / "corpus" / "chunks"
    rerun_root = tmp_path / "chunks"
    committed_files = sorted(committed_root.rglob("*.jsonl"))
    assert committed_files, "no committed chunks under data/corpus/chunks/**.jsonl"

    for committed in committed_files:
        rel = committed.relative_to(committed_root)
        rerun = rerun_root / rel
        assert rerun.is_file(), f"re-run did not produce {rel}"
        assert (
            committed.read_bytes() == rerun.read_bytes()
        ), f"byte-identity violation at {rel} — chunker output is not deterministic"


def test_manifest_hashes_match() -> None:
    """Every per-filing sha256 in MANIFEST.json matches the file bytes; tokenizer revision pinned."""
    manifest_path = _REPO_ROOT / "data" / "corpus" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Tokenizer revision pin — Pitfall 3 — prevent silent BGE drift.
    expected_rev = "982532469af0dff5df8e70b38075b0940e863662"
    assert (
        manifest["tokenizer"]["revision_hash"] == expected_rev
    ), "BGE tokenizer revision drifted from the pinned hash — Pitfall 3"

    for entry in manifest["filings"]:
        for kind in ("raw", "normalized", "chunks"):
            path_key = f"{kind}_path"
            sha_key = f"{kind}_sha256"
            file_path = _REPO_ROOT / entry[path_key]
            actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
            assert actual == entry[sha_key], (
                f"{kind} sha256 mismatch for {entry[path_key]}: "
                f"manifest={entry[sha_key]!r} actual={actual!r}"
            )
