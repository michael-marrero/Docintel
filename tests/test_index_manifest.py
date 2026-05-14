"""Wave 0 scaffold — IDX-03 MANIFEST schema + library-version + atomic-write tests.

Covers VALIDATION.md Per-Task Verification Map rows for IDX-03 (manifest carries
``embedder.{name,model_id,dim}``, ``dense.backend``, ``bm25.{library,library_version,...}``,
``corpus_manifest_sha256``, ``chunk_count``, ``built_at``, ``git_sha``,
``format_version``), Pitfall 6 (bm25s library_version recorded from
``importlib.metadata.version("bm25s")``), and Pitfall 8 / CD-08 (atomic MANIFEST
write — mid-write failure leaves the prior file intact and no orphan ``.tmp``
sibling).

Plan 04-02 landed the ``IndexManifest`` Pydantic model in ``docintel_core.types``
and Plan 04-05 landed the build pipeline + ``_atomic_write_manifest`` helper;
Plan 04-07 Task 1 removed the former xfail markers so these assertions now run
as hard tests.

Analog: ``tests/test_chunk_idempotency.py::test_manifest_hashes_match`` shape
(load MANIFEST, assert per-field invariants).
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import pytest

from docintel_index.manifest import _atomic_write_manifest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_manifest_required_fields() -> None:
    """IDX-03: MANIFEST.json carries the canonical top-level + nested fields.

    Top-level keys: ``embedder``, ``dense``, ``bm25``, ``corpus_manifest_sha256``,
    ``chunk_count``, ``built_at``, ``git_sha``, ``format_version``. The embedder
    block carries ``name``, ``model_id``, ``dim``; ``dense.backend`` is ``"numpy"``
    in stub mode and ``"qdrant"`` in real mode; the bm25 block carries
    ``library``, ``library_version``, ``k1``, ``b``, ``tokenizer``, ``vocab_size``,
    ``sha256``.
    """
    manifest_path = _REPO_ROOT / "data" / "indices" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for top in (
        "embedder",
        "dense",
        "bm25",
        "corpus_manifest_sha256",
        "chunk_count",
        "built_at",
        "git_sha",
        "format_version",
    ):
        assert top in manifest, f"MANIFEST missing top-level field {top!r}"

    for sub in ("name", "model_id", "dim"):
        assert sub in manifest["embedder"], f"MANIFEST.embedder missing {sub!r}"

    assert manifest["dense"]["backend"] in ("numpy", "qdrant"), (
        f"dense.backend must be 'numpy' (stub) or 'qdrant' (real); "
        f"got {manifest['dense'].get('backend')!r}"
    )

    for sub in ("library", "library_version", "k1", "b", "tokenizer", "vocab_size", "sha256"):
        assert sub in manifest["bm25"], f"MANIFEST.bm25 missing {sub!r}"


def test_manifest_records_library_versions() -> None:
    """Pitfall 6: ``manifest.bm25.library_version`` matches the installed bm25s version.

    Recording the library version in the MANIFEST is the structural defence
    against silent file-layout drift on a dep bump. Stub-mode builds carry a
    numpy-backed dense store; real-mode builds add ``qdrant_client_version``
    under ``dense``. This test exercises the bm25s side only because stub mode
    is the default CI path.
    """
    manifest_path = _REPO_ROOT / "data" / "indices" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    recorded = manifest["bm25"]["library_version"]
    assert recorded, "MANIFEST.bm25.library_version must be non-empty — Pitfall 6"

    installed = importlib.metadata.version("bm25s")
    assert recorded == installed, (
        f"MANIFEST.bm25.library_version ({recorded!r}) does not match installed bm25s ({installed!r}) — "
        "Pitfall 6 library-version drift"
    )


def test_atomic_write_partial_failure(tmp_path: Path) -> None:
    """Pitfall 8 / CD-08: a mid-write failure leaves the prior MANIFEST intact + no orphan .tmp.

    Simulates a SIGKILL-style interruption mid-write. The helper writes to
    ``MANIFEST.json.tmp`` then ``.replace()``-es to ``MANIFEST.json`` atomically;
    if anything raises before ``.replace()``, the destination must be unchanged
    AND the ``.tmp`` sibling must be unlinked (SUGGESTION 10 — try/finally cleanup).
    """
    dest = tmp_path / "MANIFEST.json"
    original_payload = {"format_version": "1.0", "marker": "original"}
    dest.write_text(json.dumps(original_payload, sort_keys=True), encoding="utf-8")
    original_bytes = dest.read_bytes()

    # Sentinel payload — the helper must serialise this then raise before the
    # rename step. The test substitutes a write_text that raises mid-flight via
    # a monkeypatched ``Path.replace`` — keeping the substitution local to this
    # test prevents cross-test contamination.
    class _Boom(RuntimeError):
        pass

    import unittest.mock

    with unittest.mock.patch("pathlib.Path.replace", side_effect=_Boom("simulated crash")):
        with pytest.raises(_Boom):
            _atomic_write_manifest(dest, {"format_version": "1.0", "marker": "new"})

    assert (
        dest.read_bytes() == original_bytes
    ), "_atomic_write_manifest left destination in inconsistent state after failure — Pitfall 8"
    assert not (
        tmp_path / "MANIFEST.json.tmp"
    ).exists(), "_atomic_write_manifest left orphan .tmp file after failure — SUGGESTION 10 (try/finally cleanup)"
