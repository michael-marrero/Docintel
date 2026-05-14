---
phase: 05-retrieval-hybrid-rerank
plan: 04
subsystem: retrieval
tags: [null-adapter, ablation-seam, structural-protocol, wave-1, phase-11-prefetch]
requires:
  - "Plan 05-01 Wave-0 xfail scaffold at tests/test_null_adapters.py (4 xfail-strict tests imported docintel_retrieve.null_adapters before it existed)"
  - "Plan 05-02 docintel-retrieve workspace package skeleton + __init__.py (Wave 0)"
  - "Plan 05-03 _rrf_fuse + RRF_K re-exports (preserved verbatim in __init__.py)"
  - "Phase 2 Reranker Protocol (@runtime_checkable) + RerankedDoc Pydantic shape — input contract for NullReranker.rerank"
  - "Phase 4 BM25Store Protocol (@runtime_checkable, 6 methods) — input contract for NullBM25Store"
provides:
  - "NullReranker — stateless class satisfying the Reranker Protocol structurally; .rerank(query, docs) preserves input order via score = -float(rank); .name = 'null-reranker'"
  - "NullBM25Store — stateless class satisfying the full 6-method BM25Store Protocol structurally; .query returns []; .commit returns the 64-zero sha256 sentinel; .verify returns True; .last_vocab_size returns 0; .name = 'null-bm25'"
  - "Two new re-exports on docintel_retrieve.__init__ (NullBM25Store + NullReranker) alongside Plan 05-02's RetrievedChunk and Plan 05-03's RRF_K + _rrf_fuse"
  - "Phase 11 ablation seam now constructible without touching Retriever.search — AdapterBundle(reranker=NullReranker(), ...) and IndexStoreBundle(bm25=NullBM25Store(), ...) work as adapter swaps, zero conditional branches in the hot path (D-08)"
affects:
  - "Plan 05-05 Retriever.search will compose .reranker.rerank() and .bm25.query() against bundles whose contents may be the null variants — same code path, degenerate scoring"
  - "Phase 11 ABL-01 no-rerank ablation: AdapterBundle(reranker=NullReranker(), ...) construct works without Retriever modifications"
  - "Phase 11 ABL-01 dense-only ablation: IndexStoreBundle(bm25=NullBM25Store(), ...) construct works without Retriever modifications"
  - "RET-02 ablation-seam contract is now closed at HEAD"
tech-stack:
  added: []
  patterns:
    - "Structural Protocol satisfaction with NO inheritance (PATTERNS.md Pattern S2; mirrors StubReranker, StubEmbedder, Bm25sStore) — class declared bare 'class NullReranker:' and 'class NullBM25Store:'; @runtime_checkable on the Protocol enables isinstance() verification"
    - "Score-negation trick for stable order preservation: score = -float(rank) means a downstream descending sort by score preserves the input ordering (top of input → score 0, bottom → score -(M-1))"
    - "64-character zero string as a stable sha256 sentinel — a valid hex shape that matches the Phase 4 IndexManifestBM25.sha256 field expectation, so any Phase 11 ablation manifest write produces reproducible identities without random / clock state"
    - "Zero SDK / heavy-dep imports — module loads only RerankedDoc (Pydantic) and Chunk (Pydantic), both already in core; the null adapters add no new entry to uv.lock and pay no torch/qdrant/bm25s/numpy import cost"
    - "Adapter swap is the artifact (D-08; Phase 2 D-03 precedent for Anthropic ↔ OpenAI) — Phase 5's Retriever.search has zero conditional branches for ablation, mirroring the Phase-2 pattern of provider switching via factory dispatch rather than runtime flags"
key-files:
  created:
    - "packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py"
  modified:
    - "packages/docintel-retrieve/src/docintel_retrieve/__init__.py"
    - "tests/test_null_adapters.py"
decisions:
  - "Adopted the verbatim Pattern 3 skeleton from RESEARCH.md lines 540-616 — both class bodies and the score-negation logic match the researcher's specification exactly; no invention beyond docstring elaboration."
  - "Module docstring spells out the full D-08 rationale (no conditional branches in Retriever.search), the runtime_checkable protocol-satisfaction discipline, the no-SDK-import constraint, and the RESEARCH.md 'Don't add tenacity wraps inside Retriever' anti-pattern reminder. The docstring is the contract surface for Phase 11 and a future reader who finds these classes via grep."
  - "tests/test_null_adapters.py xfail markers were entirely removed (4 xfail decorators dropped → 0 remaining; grep -c 'pytest.mark.xfail' returns 0); added the optional test_null_reranker_empty_docs edge case from the plan's <behavior> bullet so the total is 5 passing tests (within the plan's '4 or 5 passed' allowance) and tightened test_null_reranker_preserves_order to also assert original_rank equality."
  - "Did NOT inherit NullReranker / NullBM25Store from Reranker / BM25Store protocols (Python 3.11 supports Protocol inheritance; we deliberately don't use it). Rationale: every existing stub (StubReranker, StubEmbedder, Bm25sStore) uses the structural-typing pattern; the @runtime_checkable isinstance check is the contract enforcement mechanism; consistency with the codebase pattern is itself the artifact."
metrics:
  duration: "~12 minutes"
  tasks: 1
  files_created: 1
  files_modified: 2
  completed: "2026-05-14"
---

# Phase 05 Plan 04: NullReranker + NullBM25Store Ablation Seam Summary

Ship the Phase 11 ablation seam — two stateless classes (`NullReranker`, `NullBM25Store`) that satisfy the existing `Reranker` and `BM25Store` protocols structurally so Phase 11's no-rerank and dense-only ablations construct an ablated `Retriever` by **adapter swap** rather than by behavior toggle in `Retriever.search` (D-08). Closes RET-02.

## What This Plan Did

One atomic task — created `packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` with the two stateless classes; extended `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` with the two new re-exports (alphabetical `["NullBM25Store", "NullReranker", "RRF_K", "RetrievedChunk", "_rrf_fuse"]`); removed the four `@pytest.mark.xfail(strict=True, ...)` decorators that Plan 05-01 added to `tests/test_null_adapters.py` and added the optional `test_null_reranker_empty_docs` edge case enumerated in the plan's `<behavior>` block.

After this plan: `from docintel_retrieve.null_adapters import NullBM25Store, NullReranker` works; `from docintel_retrieve import NullBM25Store, NullReranker` (cross-package re-export) works; `isinstance(NullReranker(), Reranker)` and `isinstance(NullBM25Store(), BM25Store)` are both `True` at runtime (`@runtime_checkable` structural check); `NullReranker().rerank("q", ["a", "b", "c"])` returns `[RerankedDoc(doc_id="0", text="a", score=0.0, original_rank=0), RerankedDoc(doc_id="1", text="b", score=-1.0, original_rank=1), RerankedDoc(doc_id="2", text="c", score=-2.0, original_rank=2)]`; `NullBM25Store().query("q", 100) == []`, `.name == "null-bm25"`, `.commit() == "0" * 64`, `.verify() is True`, `.last_vocab_size() == 0`. `uv run pytest tests/test_null_adapters.py -ra -q` reports `5 passed, 0 xfailed, 0 failed`; full suite `uv run pytest -ra -q` reports `110 passed, 6 skipped, 10 xfailed` (xfail count drops by 4 from the Plan 05-03 baseline of 14, matching the plan's verification step 2).

## Task 1 — Two Null Adapter Classes + Atomic Re-export + xfail Flip (commit `d028748`)

Three coupled edits in one commit.

### File 1 created — `packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` (128 lines)

**Module docstring (lines 1-55):** Spells out the D-08 ablation seam pattern — two classes satisfy `Reranker` / `BM25Store` structurally but degenerate the corresponding stage; Phase 11's no-rerank ablation builds `AdapterBundle(embedder=..., reranker=NullReranker(), llm=..., judge=...)`; Phase 11's dense-only ablation builds `IndexStoreBundle(dense=..., bm25=NullBM25Store())`; Phase 5's `Retriever.search` has **zero conditional branches** for ablation. Cites the "adapter swap is the artifact" framing (Phase 2 D-03 precedent for Anthropic ↔ OpenAI); explicitly cites the RESEARCH.md "Don't add tenacity wraps inside `Retriever`" anti-pattern; declares the discipline (no SDK imports, no I/O, no env-var reads, no clock/RNG, deterministic output).

**Imports (lines 57-60):** `from __future__ import annotations`, `from docintel_core.adapters.types import RerankedDoc`, `from docintel_core.types import Chunk`. NO numpy, NO structlog, NO tenacity, NO bm25s, NO qdrant_client, NO sentence_transformers, NO torch — verified via grep gate at acceptance time (`grep -E '^(import|from)\s+(structlog|numpy|tenacity|bm25s|qdrant_client|sentence_transformers|torch)' packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` returns no matches).

**Class 1 — `NullReranker` (lines 63-92):**

```python
class NullReranker:
    """Preserve input order; satisfies the ``Reranker`` protocol structurally."""

    @property
    def name(self) -> str:
        return "null-reranker"

    def rerank(self, query: str, docs: list[str]) -> list[RerankedDoc]:
        return [
            RerankedDoc(doc_id=str(i), text=doc, score=-float(i), original_rank=i)
            for i, doc in enumerate(docs)
        ]
```

- `.name` returns `"null-reranker"` (Phase 10 eval manifest key per Phase 2 D-13).
- `.rerank(query, docs)` returns `[RerankedDoc(doc_id=str(i), text=doc, score=-float(i), original_rank=i) for i, doc in enumerate(docs)]` — single list comprehension; empty `docs` returns `[]` automatically (verified by `test_null_reranker_empty_docs`).
- **Score-negation trick:** `score = -float(rank)` means the top of the input list (rank 0) gets `score = 0.0`; the bottom of an M-element list gets `score = -(M-1)`. Phase 5's `Retriever._rerank` (to ship in Plan 05-05) sorts the reranker output descending by score (matching `BGEReranker.rerank` + `StubReranker.rerank` post-sort behaviour); with `NullReranker`, that descending sort retains the input order. The downstream sort thus has nothing to do at runtime but the *code path is identical* between rerank-enabled and rerank-ablated modes — the canary's structural defense (D-10 + D-16) tests the same control flow.

**Class 2 — `NullBM25Store` (lines 95-128):**

```python
class NullBM25Store:
    """Return zero candidates; satisfies the ``BM25Store`` protocol structurally."""

    @property
    def name(self) -> str:
        return "null-bm25"

    def add(self, chunks: list[Chunk], text: list[str]) -> None:
        """No-op — null store has no state to accumulate."""

    def commit(self) -> str:
        return "0" * 64

    def query(self, query_text: str, k: int) -> list[tuple[str, int, float]]:
        return []

    def verify(self) -> bool:
        return True

    def last_vocab_size(self) -> int:
        return 0
```

Six methods (the full BM25Store Protocol surface from `packages/docintel-core/src/docintel_core/adapters/protocols.py` lines 222-294):

| Method | Return | Rationale |
|--------|--------|-----------|
| `.name` (property) | `"null-bm25"` | Phase 10 eval manifest key per Phase 2 D-13 |
| `.add(chunks, text)` | `None` (no-op, docstring only) | Null store has no state to accumulate; matches the type signature on the Protocol so `isinstance` passes |
| `.commit()` | `"0" * 64` (64-zero hex sha256 sentinel) | Stable across calls and processes — matches the `IndexManifestBM25.sha256` field shape (hex sha256 of `index.npz`), so any Phase 11 ablation run that touches the manifest writer produces a reproducible identity for the null variant. NOT a random / clock-derived placeholder. |
| `.query(query_text, k)` | `[]` (always) | Phase 5's RRF runs over a single ranker (dense), which reduces to that ranker's ordering — the desired Phase 11 dense-only ablation semantics. The `k` parameter is honored by ignoring it (returning fewer than `k` is allowed by the Protocol contract). |
| `.verify()` | `True` (trivially) | No persisted artefact to re-hash; the verify call is a no-op in the null store. `docintel-index verify` would not be invoked with a null variant in production. |
| `.last_vocab_size()` | `0` | Vocab size is zero; Phase 4 `IndexManifestBM25.vocab_size` would surface `0` in any Phase 11 manifest emitted from a null-store run, which is the correct identity. |

**Why the 64-zero sha256 sentinel:** When Phase 11 emits an ablation manifest header (Phase 10 eval-report frontmatter style), the BM25 store's `.commit()` identity flows into `IndexManifestBM25.sha256`. A random / `os.urandom`-derived placeholder would break manifest-identity-driven cache lookups; a `None` or empty string would fail the manifest schema's hex-string shape check; the 64-zero string is unambiguous, stable across processes, and survives the Phase 4 `corpus_identity_hash` shape assertion (a 64-character lowercase hex string).

**Why structural typing (no inheritance):** Python 3.11 supports `class NullReranker(Reranker):` but every existing stub in the codebase (`StubReranker`, `StubEmbedder`, `Bm25sStore`) declares the bare `class Foo:` form. The `Reranker` and `BM25Store` Protocols are declared `@runtime_checkable` in `protocols.py`, so `isinstance(NullReranker(), Reranker)` performs the structural method-set check at runtime — that check is the contract enforcement mechanism. Consistency with the codebase pattern is itself the artifact (PATTERNS.md Pattern S2).

### File 2 modified — `packages/docintel-retrieve/src/docintel_retrieve/__init__.py`

Before (Plan 05-03 baseline):

```python
from docintel_core.types import RetrievedChunk

from docintel_retrieve.fuse import RRF_K, _rrf_fuse

__all__ = ["RRF_K", "RetrievedChunk", "_rrf_fuse"]
```

After (Plan 05-04):

```python
from docintel_core.types import RetrievedChunk

from docintel_retrieve.fuse import RRF_K, _rrf_fuse
from docintel_retrieve.null_adapters import NullBM25Store, NullReranker

__all__ = ["NullBM25Store", "NullReranker", "RRF_K", "RetrievedChunk", "_rrf_fuse"]
```

The `__all__` list stays alphabetical, preserving the Plan 05-03 sort order. The module docstring (lines 1-16) already mentions `null_adapters` per Plan 05-02 scaffolding; no docstring change.

### File 3 modified — `tests/test_null_adapters.py`

Plan 05-01 marked four tests xfail-strict (because `docintel_retrieve.null_adapters` did not yet exist). Plan 05-04 removes those four `@pytest.mark.xfail(strict=True, ...)` decorators verbatim and adds the optional `test_null_reranker_empty_docs` edge case. Final state:

| Test | Asserts |
|------|---------|
| `test_null_reranker_preserves_order` | `[d.doc_id for d in out] == ["0", "1", "2"]`, `[d.text for d in out] == ["alpha", "beta", "gamma"]`, `[d.score for d in out] == [0.0, -1.0, -2.0]`, `[d.original_rank for d in out] == [0, 1, 2]` (tightened over the Plan 05-01 baseline which only checked score) |
| `test_null_reranker_satisfies_protocol` | `isinstance(NullReranker(), Reranker)` is `True` |
| `test_null_reranker_empty_docs` (new) | `NullReranker().rerank("query", []) == []` — no exception, empty list passes through |
| `test_null_bm25_empty` | `store.query("any query", k=100) == []`, `store.name == "null-bm25"`, `store.last_vocab_size() == 0`, `store.commit() == "0" * 64`, `store.verify() is True` (tightened over the Plan 05-01 baseline to also cover `.commit` + `.verify`) |
| `test_null_bm25_satisfies_protocol` | `isinstance(NullBM25Store(), BM25Store)` is `True` |

The module docstring at the top of the file was rewritten from "Plan 05-01 Wave 0 xfail scaffolds" to "Plan 05-04 — NullReranker + NullBM25Store (Phase 5 D-08 ablation seam)" to reflect the new state.

## Verification Performed

| Check | Command | Result |
|-------|---------|--------|
| Task tests pass | `uv run pytest tests/test_null_adapters.py -ra -q` | `5 passed in 0.05s` |
| Full suite | `uv run pytest -ra -q` | `110 passed, 6 skipped, 10 xfailed` (xfail count down −4 from Plan 05-03 baseline of 14, matching the plan's verification step 2) |
| mypy strict (new module) | `uv run mypy --strict packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` | `Success: no issues found in 1 source file` |
| mypy strict (full package) | `uv run mypy --strict packages/docintel-retrieve/src/docintel_retrieve/` | `Success: no issues found in 3 source files` |
| CI grep gate 1 (index wraps) | `bash scripts/check_index_wraps.sh` | exit 0 — "OK: all real adapter files with qdrant_client calls have tenacity imports" |
| CI grep gate 2 (adapter wraps) | `bash scripts/check_adapter_wraps.sh` | exit 0 — "OK: all real adapter files with SDK calls have tenacity imports" |
| CI grep gate 3 (ingest wraps) | `bash scripts/check_ingest_wraps.sh` | exit 0 — "OK: all ingest files with sec-edgar-downloader calls have tenacity imports" |
| Cross-package re-export | `uv run python -c "from docintel_retrieve import NullReranker, NullBM25Store"` | exit 0 |
| Protocol structural check | `uv run python -c "from docintel_core.adapters.protocols import BM25Store, Reranker; from docintel_retrieve.null_adapters import NullBM25Store, NullReranker; assert isinstance(NullReranker(), Reranker); assert isinstance(NullBM25Store(), BM25Store)"` | exit 0 |
| Rerank order behavior | `uv run python -c "...assert [d.doc_id for d in r] == ['0', '1', '2']; assert [d.score for d in r] == [0.0, -1.0, -2.0]"` | exit 0 |
| BM25 surface behavior | `uv run python -c "...assert s.query('q', 100) == []; assert s.name == 'null-bm25'; assert s.commit() == '0' * 64; assert s.verify() is True; assert s.last_vocab_size() == 0"` | exit 0 |
| Source — exactly 2 null classes | `grep -cE '^class Null(Reranker\|BM25Store):' packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` | `2` |
| Source — no inheritance | `grep -E '^class Null(Reranker\|BM25Store)\(.+\):' packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` | no matches (structural typing) |
| Source — ≥6 protocol methods | `grep -cE '^\s+def (name\|add\|commit\|query\|verify\|last_vocab_size\|rerank)' packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` | `8` (NullReranker: name + rerank; NullBM25Store: name + add + commit + query + verify + last_vocab_size) |
| Source — no SDK imports | `grep -E '^(import\|from)\s+(structlog\|numpy\|tenacity\|bm25s\|qdrant_client\|sentence_transformers\|torch)' packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` | no matches |
| Source — __init__.py re-exports | `grep -F 'from docintel_retrieve.null_adapters import NullBM25Store, NullReranker' packages/docintel-retrieve/src/docintel_retrieve/__init__.py` | match |
| Source — xfail removed | `grep -c 'pytest.mark.xfail' tests/test_null_adapters.py` | `0` |

## Acceptance Criteria Status

From `05-04-PLAN.md`:

- [x] Source assertion: file `null_adapters.py` exists and declares `class NullReranker:` AND `class NullBM25Store:` exactly once each — `grep -cE '^class Null(Reranker|BM25Store):' ...` returns `2`.
- [x] Source assertion: neither class inherits from Protocol or any class — `grep -E '^class Null(Reranker|BM25Store)\(.+\):' ...` returns no matches; both are bare `class NullX:`.
- [x] Source assertion: NullBM25Store implements all six BM25Store protocol methods — `grep -cE '^\s+def (name|add|commit|query|verify|last_vocab_size)' ...` returns `≥6` (returns `8` total including NullReranker's `name`+`rerank`).
- [x] Source assertion: no SDK / heavy-dep imports — `grep -E '^(import|from)\s+(structlog|numpy|tenacity|bm25s|qdrant_client|sentence_transformers|torch)' ...` returns no matches.
- [x] Source assertion: `__init__.py` re-exports both — `grep -F` succeeds and `__all__` lists `NullBM25Store` + `NullReranker` alphabetically.
- [x] Source assertion: NO `@pytest.mark.xfail` remains in `tests/test_null_adapters.py` — `grep -c 'pytest.mark.xfail' ...` returns `0`.
- [x] Behavior: `isinstance(NullReranker(), Reranker)` AND `isinstance(NullBM25Store(), BM25Store)` both True.
- [x] Behavior: NullReranker rerank preserves order with scores `[0.0, -1.0, -2.0]`.
- [x] Behavior: NullBM25Store full method surface returns `[]`, `"null-bm25"`, `"0" * 64`, `True`, `0`.
- [x] Test command: `uv run pytest tests/test_null_adapters.py -ra -q` reports `5 passed, 0 xfailed, 0 failed`.
- [x] CLI: `uv run mypy --strict packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` exits 0.
- [x] CLI: three CI grep gates exit 0 (no new SDK call sites introduced).

## Deviations from Plan

None — the plan was executed exactly as written. The plan explicitly allowed "4 or 5 passed" tests (the empty-docs edge case being optional per the `<behavior>` block); 5 passing tests were shipped.

## Threat Flags

None — Plan 05-04 introduces no new trust boundaries (two stateless classes with no I/O, no SDK call, no env-var read, no network). The threat surface is empty by construction. The two mitigation lines from the plan's threat register (T-5-V5-04-protocol-drift and T-5-V5-04-score-order) are cashed by `test_null_bm25_satisfies_protocol` / `test_null_reranker_satisfies_protocol` (isinstance checks fail immediately on a missing method) and `test_null_reranker_preserves_order` (asserts the exact score list `[0.0, -1.0, -2.0]`).

## Known Stubs

None. The two classes are deliberately stateless "null" adapters; they are not stubs of unfinished work. Phase 11 (ABL-01) is the consumer that will exercise them in production paths.

## What Plan 05-05 Will Build On Top

- `docintel_core.adapters.factory.make_retriever(cfg)` will construct an `AdapterBundle` (via `make_adapters(cfg)`) and an `IndexStoreBundle` (via `make_index_stores(cfg)`), then return `Retriever(bundle=adapters, stores=stores)`. Phase 11 will swap in `NullReranker()` and `NullBM25Store()` at the bundle-construction site WITHOUT calling `make_retriever`.
- `Retriever.search(query, k)` will compose `bundle.embedder.embed([query])` → `stores.bm25.query(query_text, 100)` + `stores.dense.query(q_vec, 100)` → `_rrf_fuse(...)` → `bundle.reranker.rerank(query, top20_texts)` → top-K = 5. With null variants in the bundle: `stores.bm25.query` returns `[]`, RRF runs over dense-only; `bundle.reranker.rerank` preserves input order. The control flow is invariant — that invariance is what the reranker silent-truncation canary (RET-03) tests.

## Self-Check: PASSED

- File `packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` — FOUND
- File `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` (modified) — FOUND
- File `tests/test_null_adapters.py` (modified) — FOUND
- Commit `d028748` (feat(05-04): NullReranker + NullBM25Store ablation seam (Phase 5 D-08)) — FOUND in `git log --all`
