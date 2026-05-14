"""Plan 05-05 Task 2 tests for make_retriever (D-04, CD-01, D-12 + Pattern S5).

Promoted from Wave 0 xfail scaffold (Plan 05-01). Plan 05-05 ships the
``make_retriever`` factory in ``docintel_core.adapters.factory`` and this
file flips from two xfailed → two/three passed.

Covers VALIDATION.md rows 05-01-07 and 05-01-08 + the D-12 lazy-import
gate (Pattern S5):

* test_make_retriever_stub — make_retriever(Settings(llm_provider="stub"))
  returns a Retriever instance (D-04 third-sibling factory pattern alongside
  make_adapters + make_index_stores).
* test_chunk_map_eager_load — CD-01: __init__ loads the chunk_id → Chunk
  map; the cardinality matches the non-empty-line count across
  ``data/corpus/chunks/**/*.jsonl`` (T-5-V5-02 mitigation — Pitfall 7
  MANIFEST cardinality check).
* test_factory_lazy_imports_retriever_module — D-12 + Pattern S5: importing
  ``docintel_core.adapters.factory`` does NOT eagerly load
  ``docintel_retrieve``; the import lives INSIDE the ``make_retriever``
  function body so module-load cost stays cheap.

Analogs:
* ``tests/test_adapters.py`` ``test_make_adapters_stub`` (lines 152-162) —
  factory test pattern.
* ``tests/test_adapters.py`` ``test_stub_no_sdk_import`` — the D-12
  lazy-import gate test pattern.
* ``tests/test_chunk_idempotency.py`` ``_REPO_ROOT`` (line 27) — canonical
  test-relative path anchor.
* 05-PATTERNS.md ``tests/test_make_retriever.py`` section.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_make_retriever_stub() -> None:
    """D-04 — make_retriever(Settings(llm_provider='stub')) returns a Retriever."""
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings
    from docintel_retrieve.retriever import Retriever

    r = make_retriever(Settings(llm_provider="stub"))
    assert isinstance(r, Retriever)


def test_chunk_map_eager_load() -> None:
    """CD-01 — __init__ loads the chunk_id → Chunk map; size matches corpus count."""
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings

    chunks_root = _REPO_ROOT / "data" / "corpus" / "chunks"
    expected_count = 0
    for jsonl in sorted(chunks_root.rglob("*.jsonl")):
        expected_count += sum(
            1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    r = make_retriever(Settings(llm_provider="stub"))
    # The chunk_map is a private attribute on Retriever — test_make_retriever
    # is the one place we read it directly (gives Phase 11 a known seam too).
    assert len(r._chunk_map) == expected_count  # noqa: SLF001 — intentional private-attr read


def test_factory_lazy_imports_retriever_module() -> None:
    """D-12 + Pattern S5: importing factory does NOT eagerly load docintel_retrieve.

    The ``from docintel_retrieve.retriever import Retriever`` statement
    inside ``make_retriever`` must live in the function body, NOT at
    module top, so ``import docintel_core.adapters.factory`` stays cheap.
    This mirrors the Phase 2 D-12 lazy-import discipline that
    ``make_adapters`` applies to torch / sentence-transformers and that
    ``make_index_stores`` applies to qdrant_client.

    Hermetic-reset pattern: drop any cached docintel_retrieve module
    BEFORE importing the factory so a prior test that pulled in
    ``docintel_retrieve`` does not contaminate this assertion. The reset
    is safe under pytest because module imports are cached at the
    interpreter level and re-importing later in the test suite re-warms
    the cache.
    """
    import sys

    # Drop any cached docintel_retrieve modules so the test is hermetic.
    for mod in list(sys.modules):
        if mod.startswith("docintel_retrieve"):
            del sys.modules[mod]
    # Also drop docintel_core.adapters.factory so its module-load runs again.
    sys.modules.pop("docintel_core.adapters.factory", None)

    # Importing the factory must NOT pull in docintel_retrieve.
    from docintel_core.adapters import factory  # noqa: F401

    assert "docintel_retrieve" not in sys.modules, (
        "D-12 + Pattern S5: factory module top-level pulled in "
        "docintel_retrieve eagerly; the import must live inside "
        "make_retriever()."
    )
