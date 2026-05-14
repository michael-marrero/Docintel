---
phase: 05-retrieval-hybrid-rerank
plan: 05
subsystem: retrieval
tags: [retriever, hybrid-search, rrf, cross-encoder-rerank, structlog-telemetry, lazy-import, eager-load, claude-md-canary]

# Dependency graph
requires:
  - phase: 02-adapters-protocols
    provides: AdapterBundle (Embedder, Reranker, LLMClient, LLMJudge), make_adapters(cfg) sibling-factory pattern
  - phase: 03-corpus-ingestion
    provides: Chunk model with n_tokens BGE-tokenizer field + 500-token hard cap (D-10/D-11), data/corpus/chunks/**/*.jsonl artifacts (6,053 chunks)
  - phase: 04-embedding-indexing
    provides: DenseStore + BM25Store Protocols, IndexStoreBundle, make_index_stores(cfg) factory, MANIFEST.chunk_count for cardinality re-check
  - phase: 05-retrieval-hybrid-rerank (Plan 05-02)
    provides: RetrievedChunk Pydantic model (seven D-03 fields, frozen)
  - phase: 05-retrieval-hybrid-rerank (Plan 05-03)
    provides: _rrf_fuse pure helper + RRF_K=60 module constant
  - phase: 05-retrieval-hybrid-rerank (Plan 05-04)
    provides: NullReranker + NullBM25Store ablation seams (D-08)
provides:
  - "Retriever class — single-seam .search(query, k) -> list[RetrievedChunk] callable (D-02) wiring BM25 + dense → RRF → rerank → top-K"
  - "make_retriever(cfg) factory — third sibling alongside make_adapters + make_index_stores (D-04) with lazy import + string forward reference (D-12 + Pattern S5)"
  - "Pre-rerank n_tokens<=500 assertion with verbatim CLAUDE.md hard-gate quote in failure message (D-10 + Pitfall 6)"
  - "Query truncation at 64 BGE tokens with retriever_query_truncated structlog warning (D-11)"
  - "Twelve-field retriever_search_completed structlog telemetry line that Phase 9 MET-05 + Phase 11 ablation reports source from (D-12)"
  - "Zero-candidate path returns [] with retriever_search_zero_candidates warning (CD-07)"
  - "Eager chunk_id → Chunk map load + MANIFEST cardinality re-check in __init__ (CD-01 + Pitfall 7); ~180 ms one-time on the 6,053-chunk corpus"
  - "Defense-in-depth chunk_reranker_token_overflow soft warning (real-mode only) for BGE embedder ↔ bge-reranker-base XLM-R tokenizer drift (RESEARCH §3 + Pitfall 1)"
  - "_CLAUDE_MD_HARD_GATE module-level Final[str] constant — reused in Plan 05-06 canary failure message (Pitfall 6 doubled defense)"
affects: [phase-06-generation, phase-09-metrics, phase-10-eval-harness, phase-11-ablation-studies, phase-12-observability, phase-13-api-ui]

# Tech tracking
tech-stack:
  added: []  # zero new SDK deps; pure composition of Phase 2 + Phase 4 + Phases 05-02..05-04 artifacts
  patterns:
    - "Single-seam orchestrator class (D-02) — Retriever.search composes adapter calls; ablations via adapter swap (D-08), not behavior flags"
    - "Third sibling factory in docintel_core.adapters.factory (D-04) — make_retriever joins make_adapters + make_index_stores; lazy body import (Pattern S5) + string forward reference annotation + TYPE_CHECKING-only mypy hint"
    - "Module-level Final[int] pipeline constants (TOP_N_PER_RETRIEVER=100, TOP_M_RERANK=20, TOP_K_FINAL=5, QUERY_TOKEN_HARD_CAP=64) — grep-able from code review, no Settings fields (D-05/06/11)"
    - "Verbatim CLAUDE.md quote pinned in a module Final[str] constant (_CLAUDE_MD_HARD_GATE) — assertion + canary failure message both reuse it (Pitfall 6 doubled defense)"
    - "Eager-load + warm-up at construction (CD-01) — chunk_map + dense.query(zeros) + bm25.query('warmup') triggered in __init__; warm-up wrapped in try/except so empty-store test seams still construct"
    - "Defensive store-query try/except in Retriever.search — store failures surface as structlog warnings and degenerate to zero-candidate (CD-07 picks up the empty-fused case) rather than crashing search()"
    - "Defense-in-depth soft warning chunk_reranker_token_overflow (RESEARCH §3 + Pitfall 1) — real-mode only, future-proofed via getattr guards on reranker._model.tokenizer"
    - "structlog.testing.capture_logs() — canonical structlog assertion pattern (PATTERNS.md note line 1099, new ground for Phase 5; Phase 4 tests asserted on MANIFEST.json instead)"

key-files:
  created:
    - "packages/docintel-retrieve/src/docintel_retrieve/retriever.py (485 lines) — Retriever orchestrator class + 4 module constants + _CLAUDE_MD_HARD_GATE + private _truncate_query/_load_chunk_map/_check_reranker_token_overflow helpers"
    - ".planning/phases/05-retrieval-hybrid-rerank/05-05-SUMMARY.md — this file"
  modified:
    - "packages/docintel-retrieve/src/docintel_retrieve/__init__.py — Retriever added to re-exports and __all__"
    - "packages/docintel-core/src/docintel_core/adapters/factory.py — make_retriever(cfg) added as third sibling factory with TYPE_CHECKING-guarded Retriever import for mypy"
    - "packages/docintel-core/src/docintel_core/adapters/__init__.py — make_retriever added to from-import and __all__"
    - "tests/test_retriever_search.py — promoted from 5 xfailed scaffolds to 5 passing tests; test_zero_candidates uses concrete-induction tmp_path setup"
    - "tests/test_make_retriever.py — promoted from 2 xfailed scaffolds to 3 passing tests (added test_factory_lazy_imports_retriever_module for Pattern S5 gate)"
    - "tests/test_reranker_canary.py — xfail marker removed from test_failure_message_quotes_claude_md (Plan 05-05 ships _CLAUDE_MD_HARD_GATE → strict-xpass without removal blocks plan-level pytest verify)"

key-decisions:
  - "Defensive store-query try/except in Retriever.search (Rule 3 deviation) — store failures (e.g. FileNotFoundError on absent embeddings.npy in tmp_path test seam) surface as structlog warnings (retriever_bm25_query_failed / retriever_dense_query_failed) and degenerate to zero-candidate; CD-07 path picks up the empty-fused case. The plan's test_zero_candidates concrete-induction requires this behaviour."
  - "TYPE_CHECKING-guarded Retriever import in factory.py (Rule 3 deviation) — the plan author asserted no TYPE_CHECKING import was needed because the string forward reference would resolve via the function-body import. Empirically mypy --strict cannot resolve such a name; added under the existing TYPE_CHECKING guard. Runtime gate (test_factory_lazy_imports_retriever_module) still passes — TYPE_CHECKING blocks do not execute at runtime."
  - "xfail removal on test_failure_message_quotes_claude_md (Rule 3 deviation) — Plan 05-01 marked this test xfail(strict) anticipating Plan 05-06 would remove the marker. Plan 05-05 ships _CLAUDE_MD_HARD_GATE so the test passes; the strict-xpass blocks the plan-level pytest -ra -q full-suite-green verification. Removed in this plan; the other three canary xfails (test_cases_loaded, test_reranker_canary_stub_mode, test_reranker_canary_real_mode) stay — they belong to Plan 05-06."

patterns-established:
  - "Single-seam orchestrator + adapter-swap ablation — Phase 11 will construct ablated Retrievers via AdapterBundle/IndexStoreBundle swaps, not by branching inside .search()"
  - "Twelve-field telemetry envelope on every search — Phase 9 MET-05 + Phase 11 ablation reports source per-stage latency + cardinality from one structlog line"
  - "Pinned CLAUDE.md hard-gate paragraph as a module constant — Plan 05-06's canary failure message will import _CLAUDE_MD_HARD_GATE so any drift in one place trips a test elsewhere"
  - "Lazy-import discipline at factory boundaries — make_retriever's runtime import lives inside the function body; TYPE_CHECKING handles the mypy annotation. Pattern S5 is now used by all three Phase 2/4/5 factories"

requirements-completed: [RET-02, RET-04]

# Metrics
duration: 25min
completed: 2026-05-14
---

# Phase 5 Plan 05: Retriever Orchestrator + make_retriever Factory Summary

**Single-seam Retriever.search wiring BM25 + dense → RRF → bge-reranker into a 12-field-telemetry pipeline; make_retriever(cfg) lands as the third sibling factory in docintel_core.adapters.factory with lazy body import + TYPE_CHECKING-guarded mypy annotation.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-14T19:18:00Z (worktree branch creation + indices build)
- **Completed:** 2026-05-14T19:32:12Z
- **Tasks:** 2 (each with TDD RED + GREEN commits)
- **Files modified:** 6 (3 created/touched in retrieve package, 2 in core adapters, 1 in tests/test_reranker_canary.py for the Plan 05-01 xfail-removal deviation)
- **Test status:** 119 passed, 6 skipped (real-mode + gitleaks), 2 xfailed (Plan 05-06 canary driver), 0 failed, 0 xpassed
- **mypy --strict:** clean on 41 source files
- **Three CI grep gates:** all green (check_index_wraps, check_adapter_wraps, check_ingest_wraps — CD-04 confirmed)

### Latency benchmarks (stub mode, M2 MacBook)

| Operation | Cold | Warm |
|-----------|------|------|
| `make_retriever(Settings(llm_provider="stub"))` (eager chunk_map + warm-up) | ~180 ms | n/a (one-time) |
| `retriever.search("apple revenue", k=5)` | ~6 ms | ~6 ms |
| chunk_map size | 6,053 | 6,053 |

CD-09 budget (sub-2s per query in stub mode): comfortably met.

## Accomplishments

- **Retriever class** (485 lines) lands as the load-bearing Phase 5 seam — every Phase 6/10/13 consumer calls `.search(query, k) -> list[RetrievedChunk]`.
- **make_retriever(cfg) factory** lands as the third sibling alongside make_adapters + make_index_stores; the production seam for `Retriever` construction is one call.
- **Seven xfails flipped to passing** (5 in test_retriever_search.py + 2 in test_make_retriever.py) plus an additional canary-side xfail removed (test_failure_message_quotes_claude_md) because Plan 05-05's `_CLAUDE_MD_HARD_GATE` ship makes the test pass.
- **Three new test functions** ship green: test_factory_lazy_imports_retriever_module (Pattern S5 runtime gate), test_zero_candidates (CD-07 concrete induction), test_assertion_quotes_claude_md (D-10 Pitfall 6 doubled defense).
- **Twelve-field structlog telemetry envelope** wired through `.search()` — Phase 9 MET-05 + Phase 11 ablation reports can source per-stage latency + cardinality directly.
- **Defense-in-depth chunk_reranker_token_overflow soft warning** ships gated by `reranker.name == "bge-reranker-base"` — stub-mode CI skips it; real-mode tokenizer drift surfaces as observability.

## Task Commits

Each task was committed atomically via TDD RED + GREEN pairs:

1. **Task 1 RED: promote test_retriever_search.py from xfail to failing** — `81952ad` (test)
2. **Task 1 GREEN: Retriever class with D-10/D-11/D-12 + CD-01/04/07 defenses** — `ac964ad` (feat)
3. **Task 2 RED: promote test_make_retriever.py from xfail to failing** — `6adecec` (test)
4. **Task 2 GREEN: make_retriever(cfg) factory with lazy-import discipline (D-04)** — `75c4b36` (feat)

## Retriever.__init__ verbatim signature

```python
def __init__(
    self,
    bundle: AdapterBundle,
    stores: IndexStoreBundle,
    cfg: Settings,
) -> None:
```

## make_retriever verbatim signature

```python
def make_retriever(cfg: Settings) -> "Retriever":  # noqa: F821 — string forward reference (Pattern S5)
```

The return-type annotation is a **string forward reference** (`-> "Retriever"`). The runtime `from docintel_retrieve.retriever import Retriever` lives INSIDE the function body. mypy --strict resolves the string by reading the TYPE_CHECKING-only import at the top of factory.py.

## Module constants (D-05/D-06/D-11)

| Constant | Value | Decision | Cited reasoning |
|----------|-------|----------|----------------|
| `TOP_N_PER_RETRIEVER` | `100` | D-05 | BM25 + dense each return top-100; recall payoff vs 50 meaningful on 10-K boilerplate prose |
| `TOP_M_RERANK` | `20` | D-06 | bge-reranker-base on CPU ≈ 20 ms/pair → 20 pairs ≈ 0.4 s (predictable for stub + real) |
| `TOP_K_FINAL` | `5` | D-06 | Headroom over RET-03's "top-3 hit" criterion; 5-chunk context block for Phase 6 generation |
| `QUERY_TOKEN_HARD_CAP` | `64` | D-11 | Defensive cap on query length; truncation is LOUD via retriever_query_truncated structlog warn, never silent |

All four declared as `Final[int]` per the plan acceptance criteria.

## _CLAUDE_MD_HARD_GATE constant (verbatim)

```python
_CLAUDE_MD_HARD_GATE: Final[str] = (
    "Per CLAUDE.md: \"If that gate fails, look at BGE 512-token truncation "
    "FIRST before suspecting hybrid retrieval, RRF, or chunk size. This is "
    "the most common subtle failure mode and the canary exists specifically "
    "to catch it.\""
)
```

Required substrings (Pitfall 6) verified:
- `"BGE 512-token truncation FIRST"` (1 match)
- `"before suspecting hybrid retrieval, RRF, or chunk size"` (in the constant + reused in test_assertion_quotes_claude_md assertion lookup; 2 matches in retriever.py source — one in the constant string literal and one in the assertion message that re-concatenates the constant)
- `"the canary exists specifically to catch it"` (1 match)

Plan 05-06 will `from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE` inside the canary failure message so any drift in the constant trips test_failure_message_quotes_claude_md immediately (Pitfall 6 doubled defense).

## D-12 telemetry — twelve field names

The `retriever_search_completed` INFO structlog line emits the following twelve fields verbatim:

| Field | Type | Source |
|-------|------|--------|
| `query_tokens` | int | embedder-side count from _truncate_query |
| `query_truncated` | bool | `q_tokens > QUERY_TOKEN_HARD_CAP` |
| `bm25_candidates` | int | `len(bm25_results)` |
| `dense_candidates` | int | `len(dense_results)` |
| `rrf_unique` | int | `len(fused)` (set-union cardinality across both rankers) |
| `rerank_input` | int | `len(top_m_chunks)` = `min(TOP_M_RERANK, len(fused))` |
| `results_returned` | int | `len(results)` |
| `bm25_ms` | float | `round((time.perf_counter() - bm25_t0) * 1000, 2)` |
| `dense_ms` | float | same shape for the dense call |
| `fuse_ms` | float | same shape for `_rrf_fuse` |
| `rerank_ms` | float | same shape for `reranker.rerank` |
| `total_ms` | float | `round((time.perf_counter() - t0) * 1000, 2)` |

`test_telemetry_fields` asserts ALL twelve keys present; Phase 9 MET-05 will source per-stage p50/p95 latency from this single log line.

## CI grep gate status (CD-04 — no new tenacity wraps)

```
$ bash scripts/check_index_wraps.sh
OK: all real adapter files with qdrant_client calls have tenacity imports
$ bash scripts/check_adapter_wraps.sh
OK: all real adapter files with SDK calls have tenacity imports
$ bash scripts/check_ingest_wraps.sh
OK: all ingest files with sec-edgar-downloader calls have tenacity imports
```

Phase 5's `Retriever` composes already-wrapped adapter calls and adds zero `@retry` decorators. `grep -cE '^(from tenacity|@retry)' packages/docintel-retrieve/src/docintel_retrieve/retriever.py` returns 0; `grep -cE '^(from|import)\s+(bm25s|qdrant_client|sentence_transformers|torch)'` also returns 0. Neither grep gate is widened by Phase 5.

## Pattern S5 lazy-import gate (D-12)

```python
import sys
for mod in list(sys.modules):
    if mod.startswith("docintel_retrieve"):
        del sys.modules[mod]
sys.modules.pop("docintel_core.adapters.factory", None)
from docintel_core.adapters import factory
assert "docintel_retrieve" not in sys.modules  # passes
```

The `from docintel_retrieve.retriever import Retriever` runtime import in `make_retriever` lives INSIDE the function body — module-load of `docintel_core.adapters.factory` does NOT pull in `docintel_retrieve` transitively. The TYPE_CHECKING-block import (for mypy --strict) runs only under static analysis. `test_factory_lazy_imports_retriever_module` enforces the runtime gate; verified empirically via the smoke test above.

## Files Created/Modified

- `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` (NEW, 485 lines) — Retriever orchestrator class with .search seam; four Final[int] module constants; _CLAUDE_MD_HARD_GATE Final[str] constant; private _truncate_query, _load_chunk_map, _check_reranker_token_overflow helpers; defensive store-query try/except + warm-up try/except.
- `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` — Retriever added to re-exports and __all__ (alphabetical).
- `packages/docintel-core/src/docintel_core/adapters/factory.py` — make_retriever(cfg) -> "Retriever" function added with multi-line docstring; TYPE_CHECKING-only Retriever import added with explanatory comment.
- `packages/docintel-core/src/docintel_core/adapters/__init__.py` — make_retriever added to from-import and __all__ (alphabetical).
- `tests/test_retriever_search.py` — xfail markers removed; 5 test bodies implement the contract per the plan's <behavior> block; test_zero_candidates uses concrete-induction tmp_path setup.
- `tests/test_make_retriever.py` — xfail markers removed; 2 existing test bodies preserved; test_factory_lazy_imports_retriever_module added for Pattern S5 runtime gate.
- `tests/test_reranker_canary.py` — xfail marker removed from test_failure_message_quotes_claude_md (Rule 3 deviation; see Deviations section below).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Store-query try/except in Retriever.search**

- **Found during:** Task 1 GREEN — test_zero_candidates failed with FileNotFoundError on `embeddings.npy` from the empty tmp_path index.
- **Issue:** `NumpyDenseStore.query()` calls `_lazy_load_from_disk()` which raises FileNotFoundError when the dense index has not been built; the plan's test_zero_candidates concrete-induction requires `.search` to return [] gracefully.
- **Fix:** Wrapped each store query in `try/except Exception` inside `Retriever.search` Step B. Failures surface as structlog warnings (`retriever_bm25_query_failed`, `retriever_dense_query_failed`) carrying `error` + `error_type` fields and degenerate to an empty candidate list. The CD-07 zero-candidate guard then picks up the empty-fused case and emits `retriever_search_zero_candidates`.
- **Files modified:** `packages/docintel-retrieve/src/docintel_retrieve/retriever.py`
- **Commit:** `ac964ad`

**2. [Rule 3 — Blocking issue] TYPE_CHECKING-guarded Retriever import in factory.py**

- **Found during:** Task 2 GREEN — `uv run mypy --strict packages/docintel-core/src/docintel_core/adapters/factory.py` reported `error: Name "Retriever" is not defined  [name-defined]` on the `-> "Retriever":` return annotation.
- **Issue:** The plan author asserted "Do NOT add `Retriever` to the `TYPE_CHECKING` block ... mypy will resolve `"Retriever"` at type-check time by reading the function body's import." This is empirically wrong — mypy --strict cannot resolve a name imported only inside a function body when used in the function signature annotation.
- **Fix:** Added `from docintel_retrieve.retriever import Retriever` to the existing `if TYPE_CHECKING:` block at the top of factory.py with an explanatory comment noting that the TYPE_CHECKING block runs only under mypy/pyright, never at runtime, so the Pattern S5 lazy-import discipline stays intact.
- **Verification:** `test_factory_lazy_imports_retriever_module` (hermetic-reset + `assert "docintel_retrieve" not in sys.modules`) still passes — confirms the runtime gate is unaffected.
- **Files modified:** `packages/docintel-core/src/docintel_core/adapters/factory.py`
- **Commit:** `75c4b36`

**3. [Rule 3 — Blocking issue] xfail removed from test_failure_message_quotes_claude_md**

- **Found during:** Task 2 GREEN — `uv run pytest -ra -q` reported `XPASS(strict)` on `tests/test_reranker_canary.py::test_failure_message_quotes_claude_md`, which is a CI-blocking failure under pytest's `strict=True` semantics.
- **Issue:** Plan 05-01 placed `@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 05-06 implements canary driver; Plan 05-05 ships docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE which this test imports")` on the test. After Plan 05-05's `_CLAUDE_MD_HARD_GATE` ships, the test passes — turning the strict-xpass into a CI failure under the plan-level `<verification>` block ("`uv run pytest -ra -q` — full suite green").
- **Fix:** Removed the xfail decorator from this single test only. The other three Plan 05-06-owned xfails in the same file (`test_cases_loaded`, `test_reranker_canary_stub_mode`, `test_reranker_canary_real_mode`) remain — they truly belong to Plan 05-06 (canary driver + curated case file are not in Plan 05-05's scope).
- **Files modified:** `tests/test_reranker_canary.py`
- **Commit:** `75c4b36`

### Authentication gates

None — this is a pure-composition plan with no external service touch points.

## Verification status (Plan-level `<verification>` block)

| # | Gate | Status |
|---|------|--------|
| 1 | `uv run pytest tests/test_retriever_search.py tests/test_make_retriever.py -ra -q` — 7 or 8 passed | ✓ 8 passed (5 retriever_search + 3 make_retriever; the 3rd make_retriever test is the new Pattern S5 gate) |
| 2 | `uv run pytest -ra -q` — full suite green; xfail count drops by 7 from Plan 05-04 baseline | ✓ 119 passed, 6 skipped, 2 xfailed (down from 9 — drop of 7 xfails + 1 xfail-strict-xpass removal) |
| 3 | `uv run mypy --strict` — clean across all source files | ✓ Success: no issues found in 41 source files |
| 4 | `bash scripts/check_index_wraps.sh && bash scripts/check_adapter_wraps.sh && bash scripts/check_ingest_wraps.sh` — all three exit 0 | ✓ All three OK |
| 5 | `uv run python -c "from docintel_core.adapters import make_retriever; from docintel_core.config import Settings; r = make_retriever(Settings(llm_provider='stub')); results = r.search('apple revenue', k=5); assert len(results) == 5; print('OK')"` | ✓ OK (results returned in ~6 ms warm) |
| 6 | `uv run docintel-index verify` exits 0 | ✓ index_verify_clean (6,053 chunks, dense=numpy, bm25_vocab=7,520) |

## Plan-level `<success_criteria>` checklist

- ✓ Retriever class with the .search seam ships per D-02
- ✓ All four pipeline parameters pinned as module constants (D-05/06/11)
- ✓ D-10 assertion fires with verbatim CLAUDE.md quote text in failure message (Pitfall 6) — `test_assertion_quotes_claude_md` enforces both substrings
- ✓ D-11 query truncation at 64 BGE tokens emits structlog warning — `test_query_truncation_logs` enforces
- ✓ D-12 retriever_search_completed line has all twelve required fields — `test_telemetry_fields` enforces
- ✓ CD-07 zero-candidate path returns [] with structlog warning — `test_zero_candidates` enforces concrete-induction
- ✓ CD-01 eager-load: chunk_map + warm-up calls fire at __init__
- ✓ Pitfall 7 cardinality check raises ValueError on drift (with verbatim rebuild command); skipped when MANIFEST absent
- ✓ RESEARCH §3 soft warning `chunk_reranker_token_overflow` fires in real mode (stub mode skips via name guard)
- ✓ CD-04 verified: no new tenacity wraps; three CI grep gates remain green
- ✓ D-04 verified: `make_retriever` lives in docintel_core.adapters.factory with string forward reference + lazy body import
- ✓ Pattern S5 verified: importing factory module does not eagerly load docintel_retrieve (`test_factory_lazy_imports_retriever_module`)
- ✓ 7 xfails removed (5 in retriever_search + 2 in make_retriever); 8 tests pass (5 + 3 with new Pattern S5 gate)

## Threat surface scan

No new security-relevant surface introduced outside the plan's `<threat_model>`:
- No new network endpoints (no HTTP/socket surfaces; library-only).
- No new auth paths.
- No new file access patterns at trust boundaries beyond `data/corpus/chunks/**/*.jsonl` read + `data/indices/MANIFEST.json` read — both already in the `<threat_model>` (T-5-V5-02 covers the cardinality check; T-5-V5-05 covers the structlog payload).
- No new schema changes (RetrievedChunk landed in Plan 05-02; this plan only consumes it).

## Self-Check: PASSED

**Created files:**
- `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` — FOUND (485 lines)
- `.planning/phases/05-retrieval-hybrid-rerank/05-05-SUMMARY.md` — FOUND (this file)

**Modified files (presence + diff confirmed):**
- `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` — FOUND
- `packages/docintel-core/src/docintel_core/adapters/factory.py` — FOUND
- `packages/docintel-core/src/docintel_core/adapters/__init__.py` — FOUND
- `tests/test_retriever_search.py` — FOUND
- `tests/test_make_retriever.py` — FOUND
- `tests/test_reranker_canary.py` — FOUND

**Commits:**
- `81952ad` (test RED Task 1) — FOUND in `git log`
- `ac964ad` (feat GREEN Task 1) — FOUND in `git log`
- `6adecec` (test RED Task 2) — FOUND in `git log`
- `75c4b36` (feat GREEN Task 2) — FOUND in `git log`

All five-from-Task-1 + three-from-Task-2 tests pass; full suite green; mypy --strict clean; all three CI grep gates green.
