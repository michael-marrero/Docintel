"""Plan 05-01 Wave 0 xfail scaffolds for make_retriever (D-04, CD-01).

Covers VALIDATION.md rows 05-01-07 and 05-01-08 — the factory + eager-load
contract:

* test_make_retriever_stub — make_retriever(Settings(llm_provider="stub"))
  returns a Retriever instance (D-04 third-sibling factory pattern alongside
  make_adapters + make_index_stores).
* test_chunk_map_eager_load — CD-01: __init__ loads the chunk_id → Chunk map;
  the cardinality matches the non-empty-line count across
  ``data/corpus/chunks/**/*.jsonl`` (T-5-V5-02 mitigation — Pitfall 7 MANIFEST
  cardinality check).

Both tests are xfail-strict-marked because neither ``make_retriever`` nor
``docintel_retrieve.retriever.Retriever`` exist at Wave 0. The in-function
imports raise ImportError → pytest counts this as the expected failure under
xfail(strict=True). Plan 05-05 ships retriever.py + make_retriever and
removes these xfail markers.

Analogs:
* ``tests/test_adapters.py`` ``test_make_adapters_stub`` (lines 152-162) —
  factory test pattern.
* ``tests/test_chunk_idempotency.py`` ``_REPO_ROOT`` (line 27) — canonical
  test-relative path anchor.
* 05-PATTERNS.md ``tests/test_make_retriever.py`` section.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (docintel_core.adapters.factory.make_retriever + docintel_retrieve.retriever.Retriever)")
def test_make_retriever_stub() -> None:
    """D-04 — make_retriever(Settings(llm_provider='stub')) returns a Retriever (Plan 05-05)."""
    # In-function imports: neither factory nor Retriever exist at Wave 0.
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433
    from docintel_retrieve.retriever import Retriever  # noqa: WPS433 — intentional in-function import

    r = make_retriever(Settings(llm_provider="stub"))
    assert isinstance(r, Retriever)


@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-05 (CD-01 eager chunk_map load in Retriever.__init__)")
def test_chunk_map_eager_load() -> None:
    """CD-01 — __init__ loads the chunk_id → Chunk map; size matches corpus count (Plan 05-05)."""
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

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
