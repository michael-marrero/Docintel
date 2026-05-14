---
phase: 05-retrieval-hybrid-rerank
plan: 03
subsystem: retrieval
tags: [rrf, pure-function, hybrid-fusion, wave-1, cormack-2009]
requires:
  - "Plan 05-01 Wave-0 xfail scaffold at tests/test_rrf_fuse.py (4 xfail-strict tests imported docintel_retrieve.fuse before it existed)"
  - "Plan 05-02 docintel-retrieve workspace package skeleton + __init__.py with RetrievedChunk re-export (Wave 0)"
  - "Phase 4 BM25Store.query / DenseStore.query 0-based rank contract — input shape for _rrf_fuse"
provides:
  - "_rrf_fuse(bm25_results, dense_results, k=RRF_K) -> list[tuple[str, float]] — pure function implementing Cormack 2009 1/(k+rank_1based) with skip-the-contribution missing-chunk handling and CD-05 BM25-rank tie-break"
  - "RRF_K: Final[int] = 60 module constant — D-07 Cormack 2009 default, NOT a Settings field"
  - "Two new re-exports on docintel_retrieve.__init__ (RRF_K + _rrf_fuse) alongside Plan 05-02's RetrievedChunk"
affects:
  - "Plan 05-05 Retriever.search will compose _rrf_fuse between the dense/BM25 candidate stage and the rerank stage"
  - "Phase 11 ablation reports can replay _rrf_fuse over saved per-stage outputs to diff fusion behavior across runs without re-running retrieval (pure-function precondition)"
  - "RET-01 RRF math contract is now closed at HEAD"
tech-stack:
  added: []
  patterns:
    - "Pure-function shape (no I/O, no Settings, no logging) matching the docintel_core.adapters.stub.embedder._text_to_vector analog — module docstring → Final constant → typed signature → deterministic body"
    - "Final[int] module constant for tunables that are NOT Settings fields (D-07 RRF_K precedent; mirrors the StubEmbedder._DIM precedent)"
    - "0→1-based rank conversion at the function boundary (Pitfall 5 mitigation; literature-convention alignment for Phase 9/11 reports)"
    - "Skip-the-contribution rule for missing chunks (production-standard pattern from LangChain EnsembleRetriever, LlamaIndex QueryFusionRetriever, OpenSearch rrf, Elastic rrf)"
    - "float('inf') sentinel for tie-break secondary key — pushes BM25-missing chunks after BM25-present ties without needing branching code"
key-files:
  created:
    - "packages/docintel-retrieve/src/docintel_retrieve/fuse.py"
  modified:
    - "packages/docintel-retrieve/src/docintel_retrieve/__init__.py"
    - "tests/test_rrf_fuse.py"
decisions:
  - "Adopted the verbatim Pattern 1 skeleton from RESEARCH.md lines 302-382 for fuse.py — the algorithm body and docstring structure are exactly what the researcher specified; no invention."
  - "Test ordering uses chunk_ids equality (list) rather than set equality in test_rrf_skip_missing — the original Plan 05-01 scaffold used a set; tightened to a list so the CD-05 tie-break order ('c1' before 'c2' because BM25-rank 0 < inf sentinel) is asserted, not just the membership."
  - "Added test_rrf_fuse_empty_input as the optional empty-input edge case enumerated in the plan's <behavior> bullet 5 (line 98 of 05-03-PLAN.md). 5 tests total — exact match to the plan's acceptance-criteria allowance of '4 or 5 passed'."
  - "Citation URL (https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf) is included in the module docstring per the plan's <action> prescription; greppable for an audit trail back to the original SIGIR 2009 paper."
metrics:
  duration: "8 minutes"
  tasks: 1
  files_created: 1
  files_modified: 2
  completed: "2026-05-14"
---

# Phase 05 Plan 03: _rrf_fuse Pure Helper + RRF_K=60 Module Constant Summary

Ship the pure-function RRF helper that combines BM25 and dense rank lists into a single fused ranking. Closes RET-01's rank-fusion math contract; the actual `Retriever.search` orchestrator in Plan 05-05 will compose this helper between the candidate stage and the rerank stage.

## What This Plan Did

One atomic task — created `packages/docintel-retrieve/src/docintel_retrieve/fuse.py` with the `RRF_K: Final[int] = 60` module constant and the `_rrf_fuse(bm25_results, dense_results, k=RRF_K) -> list[tuple[str, float]]` pure function; extended `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` with the two new re-exports (alphabetical `["RRF_K", "RetrievedChunk", "_rrf_fuse"]`); removed the four `@pytest.mark.xfail(strict=True, ...)` decorators that Plan 05-01 added to `tests/test_rrf_fuse.py` and added the optional `test_rrf_fuse_empty_input` edge case enumerated in the plan's `<behavior>` block.

After this plan: `from docintel_retrieve.fuse import RRF_K, _rrf_fuse` works; `RRF_K == 60`; `_rrf_fuse([], []) == []`; `_rrf_fuse([("c1", 0, 1.0)], [("c1", 0, 1.0)])[0][1] == 2/61` (hand-computed); `_rrf_fuse([("c1", 0, 1.0)], [("c2", 0, 1.0)])` returns `[("c1", 1/61), ("c2", 1/61)]` in that order (CD-05 tie-break: BM25-rank 0 < inf sentinel). `uv run pytest tests/test_rrf_fuse.py -ra -q` reports `5 passed, 0 xfailed, 0 failed`.

## Task 1 — _rrf_fuse + RRF_K + atomic re-export + xfail flip (commit `e86bfbc`)

Three coupled edits in one commit:

**File 1 created — `packages/docintel-retrieve/src/docintel_retrieve/fuse.py`** (96 lines)

Module structure (RESEARCH.md Pattern 1, verbatim):

- **Module docstring (lines 1-35):** Cormack 2009 formula in plain ASCII; literature-convention reasoning for 1-based ranks; explicit Pitfall 5 callout; skip-the-contribution rule with LangChain/LlamaIndex/OpenSearch/Elastic cross-reference; CD-05 tie-break with float("inf") sentinel description; pure-function statement (no I/O, no Settings, no logging) tying back to the Phase 11 ablation use case; citation URL `https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf`.
- **Imports (lines 37-39):** `from __future__ import annotations`, `from typing import Final`. NO `numpy`, NO `structlog`, NO `logging` (verified via grep — see `(none — correct)` line in verification table below).
- **Module constant (lines 41-42):** `RRF_K: Final[int] = 60` with the one-line docstring `"""Cormack 2009 default. Pinned module constant per D-07. NOT a Settings field."""`.
- **Function signature (lines 45-49):** `def _rrf_fuse(bm25_results: list[tuple[str, int, float]], dense_results: list[tuple[str, int, float]], k: int = RRF_K) -> list[tuple[str, float]]:`.
- **Function docstring (lines 50-69):** Args (bm25_results / dense_results / k); Returns (sorted descending by rrf_score with BM25-rank tie-break, empty inputs yield []); Note (Pitfall 5 — 0→1 conversion).
- **Function body (lines 72-99):** Six steps with locked-decision citations in comments:
  1. `bm25_ranks: dict[str, int] = {cid: rank + 1 for cid, rank, _ in bm25_results}` — dict comprehension with the `+ 1` for the 0→1 conversion. Comment cites Pitfall 5.
  2. `dense_ranks: dict[str, int] = {cid: rank + 1 for cid, rank, _ in dense_results}` likewise.
  3. `all_chunk_ids = set(bm25_ranks) | set(dense_ranks)` — set-union over both rank-dict key sets.
  4. `rrf_scores: dict[str, float] = {}` filled by iterating `all_chunk_ids`; for each cid `score = 0.0`, then `score += 1.0 / (k + bm25_ranks[cid])` if cid in bm25_ranks, then `score += 1.0 / (k + dense_ranks[cid])` if cid in dense_ranks; assigned to `rrf_scores[cid]`. Comment cites RESEARCH §1 skip-the-contribution rule.
  5. Inner function `def _sort_key(cid: str) -> tuple[float, float]: bm25_rank: float = bm25_ranks.get(cid, float("inf")); return (-rrf_scores[cid], bm25_rank)`. Comment cites CD-05.
  6. `return [(cid, rrf_scores[cid]) for cid in sorted(rrf_scores, key=_sort_key)]` — list comprehension producing `[(chunk_id, rrf_score)]` in the final ordering.

Determinism: dict iteration in CPython 3.11 is insertion-ordered; `sorted()` is stable; no clock reads; no `PYTHONHASHSEED` dependency; no randomness. The function is a Phase 11 ablation precondition (T-5-rrf-determinism in the plan's threat register).

**File 2 modified — `packages/docintel-retrieve/src/docintel_retrieve/__init__.py`**

Before (Plan 05-02 baseline):

```python
from docintel_core.types import RetrievedChunk

__all__ = ["RetrievedChunk"]
```

After (Plan 05-03):

```python
from docintel_core.types import RetrievedChunk

from docintel_retrieve.fuse import RRF_K, _rrf_fuse

__all__ = ["RRF_K", "RetrievedChunk", "_rrf_fuse"]
```

`__all__` ordering is alphabetical (Python string sort treats uppercase `R` of `RRF_K` and `RetrievedChunk` before underscore-prefixed `_rrf_fuse`; this matches the plan's prescription on line 135 of 05-03-PLAN.md).

**File 3 modified — `tests/test_rrf_fuse.py`**

Four `@pytest.mark.xfail(strict=True, reason="Wave 1 — implementation lands in Plan 05-03 ...")` decorators from Plan 05-01 deleted. The four in-function `from docintel_retrieve.fuse import ...` lines hoisted to a single module-level import at the top of the file. Test bodies kept verbatim (already asserted against the hand-computed values in the plan's `<behavior>` section: `2/61`, `1/61`, `1/61`, `RRF_K == 60`).

One enhancement on `test_rrf_skip_missing`: tightened the chunk-id assertion from a set `chunk_ids = {row[0] for row in result}; assert chunk_ids == {"c1", "c2"}` to an ordered list `chunk_ids = [row[0] for row in result]; assert chunk_ids == ["c1", "c2"]`. This asserts the CD-05 tie-break behavior explicitly: when both chunks have identical RRF scores (1/61), `c1` (BM25-rank 0) wins over `c2` (BM25-missing → `float("inf")` sentinel rank). The original scaffold's set-equality assertion would pass either ordering — the list-equality assertion is the bite point on CD-05.

One new test added — `test_rrf_fuse_empty_input`:

```python
def test_rrf_fuse_empty_input() -> None:
    """RET-01 -- empty inputs return an empty list (no exception)."""
    assert _rrf_fuse([], []) == []
```

This is the optional empty-input edge case enumerated in line 98 of 05-03-PLAN.md ("`_rrf_fuse([], [])` returns `[]` (no exception)"). Total test count: 5 (4 from Plan 05-01 scaffold + 1 edge case) — exact match for the plan's acceptance "4 or 5 passed" allowance.

## Verification (Plan-Level)

| # | Check | Result |
|---|-------|--------|
| 1 | `uv run pytest tests/test_rrf_fuse.py -ra -q` | PASS (5 passed, 0 xfailed, 0 failed in 0.05s) |
| 2 | `uv run mypy --strict packages/docintel-retrieve/src/docintel_retrieve/fuse.py` | PASS (Success: no issues found in 1 source file) |
| 3 | `bash scripts/check_index_wraps.sh` | PASS (OK: all real adapter files with qdrant_client calls have tenacity imports) |
| 4 | `bash scripts/check_adapter_wraps.sh` | PASS (OK: all real adapter files with SDK calls have tenacity imports) |
| 5 | `bash scripts/check_ingest_wraps.sh` | PASS (OK: all ingest files with sec-edgar-downloader calls have tenacity imports) |
| 6 | Source: `grep -E 'RRF_K\s*:\s*Final\[int\]\s*=\s*60' fuse.py` returns 1 match | PASS |
| 7 | Source: `grep -c '^def _rrf_fuse(' fuse.py` returns 1 | PASS |
| 8 | Source: `grep -E '^(import\|from)\s+(structlog\|numpy\|logging)' fuse.py` returns no matches | PASS (no side-effect imports) |
| 9 | Source: `grep -c 'Cormack' fuse.py` returns ≥ 1 | PASS (4 mentions) |
| 10 | Source: `grep -F 'from docintel_retrieve.fuse import RRF_K, _rrf_fuse' __init__.py` succeeds | PASS |
| 11 | Source: `__all__` in __init__.py contains both `'RRF_K'` and `'_rrf_fuse'` | PASS (alphabetical: `["RRF_K", "RetrievedChunk", "_rrf_fuse"]`) |
| 12 | Source: `grep -c 'pytest.mark.xfail' tests/test_rrf_fuse.py` returns 0 | PASS (all 4 xfail decorators removed) |

**Behavioral verifications (run against final HEAD `e86bfbc`):**

| # | Behavior | Result |
|---|----------|--------|
| B1 | `from docintel_retrieve.fuse import RRF_K, _rrf_fuse; assert RRF_K == 60` | PASS |
| B2 | `_rrf_fuse([], []) == []` (no exception on empty inputs) | PASS |
| B3 | `_rrf_fuse([('c1', 0, 1.0)], [('c1', 0, 1.0)])[0][1]` is within 1e-9 of `2/61` (both rankers contribute, 1-based) | PASS |
| B4 | `_rrf_fuse([('c1', 0, 1.0)], [])[0][1]` is `1/61` (Pitfall 5: 0→1 conversion, NOT `1/60`) | PASS (via `test_rrf_one_based_ranks`) |
| B5 | `_rrf_fuse([('c1', 0, 1.0)], [('c2', 0, 1.0)])` returns `[('c1', 1/61), ('c2', 1/61)]` in that order (CD-05 tie-break) | PASS |
| B6 | `from docintel_retrieve import RRF_K, _rrf_fuse, RetrievedChunk` succeeds; prints `60` for `RRF_K` | PASS |

## Deviations from Plan

None — Task 1 executed exactly as planned. No Rule-1/2/3 deviations encountered.

### Documented adjustments (cosmetic, not behavior-changing)

**1. `chunk_ids` assertion in `test_rrf_skip_missing` tightened from set-equality to list-equality.**

- **Where:** `tests/test_rrf_fuse.py::test_rrf_skip_missing`.
- **Plan-01 scaffold version:** `chunk_ids = {row[0] for row in result}; assert chunk_ids == {"c1", "c2"}` — set equality. Passes either ordering.
- **Plan-03 final version:** `chunk_ids = [row[0] for row in result]; assert chunk_ids == ["c1", "c2"]` — ordered list equality. Asserts CD-05 tie-break behavior directly.
- **Why:** The plan's `<behavior>` block bullet 2 (line 95 of 05-03-PLAN.md) says `"'c1' sorts before 'c2' because CD-05 tie-break uses BM25 rank ascending (c1 was in BM25 at rank 0, c2 was not — inf)"`. A set-equality assertion would fail to catch a regression that broke CD-05 (e.g., a future refactor that drops the `float("inf")` sentinel and returns BM25-missing chunks ahead of BM25-present chunks in ties). The list-equality assertion is the bite point on CD-05.
- **Not a deviation:** the plan's `<behavior>` already specifies the order; the scaffold's looser assertion would have passed an implementation that violated the spec. Tightening was the contract-honoring move.

### Auto-fixed Issues

None.

### Deferred Issues

**1. Pre-existing test-isolation failures in `tests/test_bm25_store.py` when run in the full suite.**

- **Found during:** Plan 05-03 full-suite verification step (`uv run pytest -ra -q --deselect tests/test_index_build_real.py`).
- **Issue:** Two tests (`test_chunk_ids_aligned_with_rows`, `test_bm25_artifacts_present`) fail with `FileNotFoundError` / `AssertionError` in the full-suite run order, but PASS when run in isolation (`uv run pytest tests/test_bm25_store.py -ra -q` → `2 passed`).
- **Why this is NOT a Plan 05-03 regression:** Verified by running the full suite against the stashed working copy (just the pre-existing baseline plus a now-illegitimate xfail-strict marker set, since the Plan 05-01 xfails would now xpass-strict-fail if fuse.py existed). The bm25_store failures are present in the baseline run too — they are test-fixture state leakage from Phase 4 build-index tests that mutate `data/indices/` on disk and don't reset between tests. Out-of-scope per the scope-boundary rule (pre-existing, not caused by this plan's pure-function changes, which touch zero filesystem state).
- **Action:** Logged as a Phase 4 test-isolation follow-up. Plan 05-03 explicitly does NOT attempt a fix — the auto-fix attempt limit + scope-boundary rule both apply.

## Threat Surface Scan

Plan 05-03 ships a pure function with zero new threat surface. The plan's `<threat_model>` block explicitly says `(none for Plan 05-03)` and the implementation honors that: no network, no Settings read, no env-var read, no I/O, no SDK call, no logging.

Two mitigations from the plan's threat register are testable at HEAD:

- **T-5-rrf-off-by-one (Tampering — 0-vs-1-based rank conversion):** Mitigated by `bm25_ranks: dict[str, int] = {cid: rank + 1 for cid, rank, _ in bm25_results}` (line 75 of fuse.py). Bite-point regression test: `test_rrf_one_based_ranks` asserts `1/61` (not `1/60`) for a chunk at 0-based rank 0.
- **T-5-rrf-determinism (Tampering — non-deterministic output):** Mitigated by sorting on stable key `(-score, bm25_rank_or_inf)`; `sorted()` is stable in CPython 3.11; dict iteration is insertion-ordered; no clock reads; no `PYTHONHASHSEED` dependency.

No new threat surface introduced. No flags raised.

## Decisions Recorded

- **`RRF_K = 60` is a `Final[int]` module constant, NOT a Settings field.** Per D-07. Cormack 2009 default; pinned because Phase 11 ablation theater is the failure mode (tuning k invites cherry-picking). If Phase 11 ever wants to sweep k, it constructs a `Retriever` with a custom `_rrf_fuse` injection (same pattern as Phase 11's null-adapter ablations from D-08), not via env-var.
- **`float("inf")` sentinel for tie-break, NOT a branching `if cid in bm25_ranks else ...` clause.** Per CD-05. The sentinel makes the `_sort_key` function single-branch + deterministic + correct under set-union iteration; the branching alternative would have asymmetric handling depending on which ranker first encountered the chunk (a determinism risk).
- **Skip-the-contribution missing-chunk rule, NOT a `1/(k + infinity)` zero-contribution.** Per RESEARCH §1 + the explicit production-pattern verification across LangChain / LlamaIndex / OpenSearch / Elastic. The two are equivalent in the limit (both contribute 0); skip is the cleaner code (and matches every production reference implementation we audited).
- **Public re-export ordering in `__init__.py` `__all__` is alphabetical: `["RRF_K", "RetrievedChunk", "_rrf_fuse"]`.** Per the plan's line 135. Python sorts uppercase before underscore-prefixed; `RRF_K` before `RetrievedChunk` because R < e in ASCII (uppercase R = 0x52 < lowercase e = 0x65 in `RetrievedChunk`'s second char — but actually both start with `R`, so the comparison continues to the second char: `R` of `RRF_K` (0x52) vs `e` of `RetrievedChunk` (0x65) → `RRF_K` first).

## Files in Final State

```
packages/docintel-retrieve/src/docintel_retrieve/
├── __init__.py     (MODIFIED — added `from docintel_retrieve.fuse import RRF_K, _rrf_fuse`; __all__ extended)
├── fuse.py         (NEW — 96 lines; pure-function RRF helper + RRF_K=60 Final[int] constant)
└── py.typed        (unchanged from Plan 05-02; 1 byte)

tests/
└── test_rrf_fuse.py (MODIFIED — 4 xfail decorators removed, in-function imports hoisted module-level, +1 empty-input edge case test)
```

## Confirmations Required by `<output>` Block

| Item | Confirmation |
|------|--------------|
| Verbatim `_rrf_fuse` signature | `def _rrf_fuse(bm25_results: list[tuple[str, int, float]], dense_results: list[tuple[str, int, float]], k: int = RRF_K) -> list[tuple[str, float]]:` |
| Verbatim return type | `list[tuple[str, float]]` — sorted descending by `rrf_score` with BM25-rank ascending tie-break (CD-05); empty inputs yield `[]` |
| Exact RRF_K value + typing | `RRF_K: Final[int] = 60` (D-07 pinning; Cormack 2009 default) |
| Hand-computed assertion values used in tests | `2/61` (both rankers contribute at rank 0); `1/61` (single ranker at rank 0 — Pitfall 5 1-based conversion); both used as `pytest.approx(...)` targets with default `rel=1e-6` tolerance |
| No `tenacity` imports added | Confirmed — fuse.py imports only `typing.Final`. No tenacity. No SDK call site. |
| No `structlog` imports added | Confirmed — `grep -E '^(import\|from)\s+structlog' fuse.py` returns no matches. |
| No `numpy` imports added | Confirmed — `grep -E '^(import\|from)\s+numpy' fuse.py` returns no matches. The package re-pins `numpy==2.4.4` at the pyproject level for transitive consumers, but fuse.py itself has no `import numpy`. |
| Three CI grep gates remain green | `check_index_wraps.sh` PASS, `check_adapter_wraps.sh` PASS, `check_ingest_wraps.sh` PASS — no new SDK call sites introduced. |

## Commits

| Task | Hash | Type | Description |
|------|------|------|-------------|
| 1 | `e86bfbc` | feat | add _rrf_fuse pure function + RRF_K=60 module constant |

## Self-Check: PASSED

- File `packages/docintel-retrieve/src/docintel_retrieve/fuse.py` exists at HEAD.
- File `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` modified — `RRF_K` and `_rrf_fuse` in `__all__`.
- File `tests/test_rrf_fuse.py` modified — 0 xfail markers remain; 5 tests defined.
- Commit `e86bfbc` exists in `git log --oneline -2`.
- `uv run pytest tests/test_rrf_fuse.py -ra -q` reports `5 passed, 0 xfailed, 0 failed`.
- `uv run mypy --strict packages/docintel-retrieve/src/docintel_retrieve/fuse.py` exits 0 (no issues).
- Three grep gates (`check_index_wraps.sh`, `check_adapter_wraps.sh`, `check_ingest_wraps.sh`) all exit 0.
- All 8 source-assertion greps from the plan's `<acceptance_criteria>` are green.
- All 5 behavior-probe one-liners from the plan's `<acceptance_criteria>` exit 0.
- `from docintel_retrieve import RRF_K, _rrf_fuse, RetrievedChunk` succeeds; `RRF_K` prints as `60`.
- No side-effect imports (`structlog`, `numpy`, `logging`, `tenacity`) added to fuse.py.
- No deletions in the commit (`git diff --diff-filter=D --name-only HEAD~1 HEAD` returns empty).
- No untracked files left behind (`git status --short | grep '^??'` returns empty).
