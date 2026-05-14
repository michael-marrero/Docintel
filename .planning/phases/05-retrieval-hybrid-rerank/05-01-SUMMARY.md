---
phase: 05-retrieval-hybrid-rerank
plan: 01
subsystem: testing
tags: [pytest, xfail, structlog, jsonl, canary, rrf, reranker, hybrid-retrieval, ablation-seam, pydantic, protocol]

# Dependency graph
requires:
  - phase: 04-embedding-indexing
    provides: "AdapterBundle + IndexStoreBundle protocols; @pytest.mark.real marker registered; data/corpus/chunks/**/*.jsonl committed-data layout; tests/test_index_build_real.py real-mode marker analog; tests/test_chunk_idempotency.py _REPO_ROOT path-anchor analog"
  - phase: 02-adapters-protocols
    provides: "Reranker + BM25Store @runtime_checkable Protocols (for D-08 NullReranker / NullBM25Store isinstance checks in Plan 05-04); StubReranker cosine-over-hash-embeddings pattern (for D-15 stub-mode canary feasibility); make_adapters factory (sibling pattern for D-04 make_retriever)"
provides:
  - "6 new xfail-marked test files under tests/ — every test function name verbatim from 05-VALIDATION.md Per-Task Verification Map rows 05-01-01..05-03-04 (23 functions total: 14 unit + 5 integration + 4 canary)"
  - "data/eval/canary/cases.jsonl committed JSONL fixture with 1 Wave 0 placeholder record (Plan 05-06 replaces with curated >= 7 cases per D-13/D-14/D-17)"
  - "CLAUDE.md Phase 5 hard-gate paragraph now contains all three verbatim substrings (BGE 512-token truncation FIRST + before suspecting hybrid retrieval, RRF, or chunk size + the canary exists specifically to catch it) — aligns CLAUDE.md with CONTEXT.md D-16 verbatim claim and ROADMAP.md line 170"
  - "Anchored in-function import hook (from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE) inside test_failure_message_quotes_claude_md — makes the xfail naturally fail at Wave 0 (ImportError) and naturally resolve at Wave 2 (Plan 05-05 ships retriever.py)"
  - "_CLAUDE_MD_QUOTE module constant in tests/test_reranker_canary.py — verbatim canonical text for the canary failure message; doubled defense for Pitfall 6 against future cleanup PRs softening the wording"
  - "data/eval/ directory tree (new for Phase 5; sibling slot for future Phase 8 data/eval/ground_truth/ and Phase 10 data/eval/reports/)"
affects: [05-retrieval-hybrid-rerank Wave 1+ (Plans 05-02, 05-03, 05-04, 05-05, 05-06, 05-07 all flip xfails), 08-ground-truth (data/eval/ tree convention), 10-eval-harness (eval reports use same data/eval/ root)]

# Tech tracking
tech-stack:
  added: []  # Plan 05-01 added zero runtime dependencies; only test files + 1 data fixture
  patterns:
    - "Wave-0 xfail-strict scaffold pattern: deferred in-function imports raise ImportError → pytest counts as expected failure under @pytest.mark.xfail(strict=True). Wave 1+ plans remove the markers as implementations land. Each test function name verbatim from 05-VALIDATION.md so traceability holds."
    - "Function-level @pytest.mark.real + @pytest.mark.xfail marker stacking (outer / inner) — coexists with stub-mode tests in the same file; replaces Phase 4's module-level pytestmark for dual-mode test files (RESEARCH.md §9 Pattern A)."
    - "Anchored xfail-hook pattern: in-function import of a future module constant — the ImportError at Wave 0 is the xfail signal; the import resolution at the implementation wave is the natural xpass + marker-removal trigger. Pattern is wave-flip-safe."
    - "structlog.testing.capture_logs() context manager for asserting on structured log records (new for Phase 5; no Phase 4 analog because Phase 4 asserted on resulting MANIFEST.json files instead)."
    - "Verbatim canonical text as module constants in both production code (retriever._CLAUDE_MD_HARD_GATE — Plan 05-05) and test code (test_reranker_canary._CLAUDE_MD_QUOTE) — Pitfall 6 doubled defense; grep-asserts in CI catch any drift across the 5 sources (CLAUDE.md, ROADMAP.md, CONTEXT.md, retriever constant, test constant)."

key-files:
  created:
    - "tests/test_rrf_fuse.py — 4 xfail scaffolds for RET-01 (Plan 05-03 flips)"
    - "tests/test_null_adapters.py — 4 xfail scaffolds for D-08 (Plan 05-04 flips)"
    - "tests/test_retrieved_chunk_schema.py — 4 xfail scaffolds for RET-04 (Plan 05-02 flips)"
    - "tests/test_make_retriever.py — 2 xfail scaffolds for D-04 + CD-01 (Plan 05-05 flips)"
    - "tests/test_retriever_search.py — 5 xfail scaffolds for RET-02 + CD-07 (Plan 05-05 flips)"
    - "tests/test_reranker_canary.py — 4 xfail scaffolds for RET-03 (Plan 05-06 flips)"
    - "data/eval/canary/cases.jsonl — Wave 0 placeholder (Plan 05-06 replaces with curated cases)"
  modified:
    - "CLAUDE.md — Phase 5 hard-gate bullet extended by one sentence (single-character-precise edit; +1/-1 line)"

key-decisions:
  - "Multi-line @pytest.mark.xfail decorators reformatted to single-line so the plan's verbatim grep `grep -B1 \"^def test_\" | grep -c \"xfail(strict=True\"` returns the expected 14 / 9 counts without false negatives from Python's typical multi-line formatter style."
  - "test_reranker_canary_real_mode marker order is @pytest.mark.real (outer) + @pytest.mark.xfail (inner) per RESEARCH.md §9 Pattern A — pytest's marker-collection layer evaluates `not real` deselection BEFORE applying the xfail. Module-level pytestmark would gate stub-mode tests too, breaking D-15."
  - "Anchored hook for test_failure_message_quotes_claude_md uses in-function import of _CLAUDE_MD_HARD_GATE (NOT module-top). Module-top would make pytest collection itself fail at Wave 0 (ImportError on collection) rather than xfail the individual test, which would break the entire test_reranker_canary.py file's collection. In-function is the wave-flip-safe pattern."
  - "Wave 0 cases.jsonl ships 1 placeholder record (not 5+) — the test_cases_loaded xfail (strict=True) catches the < 5 floor as the expected failure at Wave 0 and naturally xpasses when Plan 05-06 lands the curated 7+ cases. This is the plan's intended `>= 5 enforcement at Wave 2` semantic."

patterns-established:
  - "Pattern: every test in 6 new files = verbatim function name from 05-VALIDATION.md → grep-friendly traceability for Wave 1+ wave-flip discipline."
  - "Pattern: in-function deferred imports for symbols that don't yet exist at Wave 0 → ImportError = xfail-strict signal, naturally resolves when implementation lands."
  - "Pattern: data/eval/canary/cases.jsonl as committed JSONL fixture (one JSON object per line, no comments, no trailing whitespace) — sibling slot to future data/eval/ground_truth/ (Phase 8) and data/eval/reports/ (Phase 10)."

requirements-completed: [RET-01, RET-02, RET-03, RET-04]
# Note: Plan 05-01 lands SCAFFOLDS for these requirements only (xfail-marked test stubs +
# CLAUDE.md alignment + canary fixture placeholder). Final implementations land in Plans
# 05-02 through 05-06; the requirements as a whole close at Wave 2 (Plan 05-06) when the
# canary fully flips green. Per the planner's choice in 05-01-PLAN.md frontmatter, these
# requirement IDs are claimed by Plan 05-01 (it's the first plan to touch them); the
# verifier runs after Wave 2 completes.

# Metrics
duration: "~13 min"
completed: 2026-05-14
---

# Phase 5 Plan 01: Wave-0 test scaffolds + canary fixture + CLAUDE.md alignment Summary

**23 xfail-strict pytest scaffolds across 6 new files for RET-01..04, the committed `data/eval/canary/cases.jsonl` placeholder, and a single-sentence CLAUDE.md extension that aligns the project guide with CONTEXT.md D-16's verbatim claim — every Wave 1+ implementation plan now has a target to flip from xfail to xpass.**

## Performance

- **Duration:** ~13 min (Task 0: 14:41, Task 1: 14:46, Task 2: 14:51 — first commit through final commit)
- **Started:** 2026-05-14T14:39Z (read of PLAN + analog files)
- **Completed:** 2026-05-14T14:52Z (final commit a3dd107)
- **Tasks:** 3 (Task 0 — CLAUDE.md edit; Task 1 — 4 unit test scaffolds; Task 2 — 2 integration test scaffolds + cases.jsonl)
- **Files modified:** 1 (CLAUDE.md, +1/-1 line)
- **Files created:** 7 (6 test files + 1 JSONL fixture)

## Accomplishments

- **23 xfail-strict pytest scaffolds** across 6 new test files, every function name verbatim from 05-VALIDATION.md Per-Task Verification Map (rows 05-01-01..05-03-04). Full Phase 5 quick-suite runs in 0.12s and reports `22 xfailed + 1 deselected` (real-mode test correctly gated behind `-m real`).
- **CLAUDE.md aligned with CONTEXT.md D-16 + ROADMAP.md line 170** — Phase 5 hard-gate bullet now carries all three verbatim canary substrings. The downstream grep-asserts in Plan 05-05's `_CLAUDE_MD_HARD_GATE` module constant and Plan 05-06's `_CLAUDE_MD_QUOTE` module constant now operate against a CLAUDE.md that genuinely contains the verbatim text.
- **Anchored in-function import hook** inside `test_failure_message_quotes_claude_md` — the canonical pattern for wave-flip-safe xfail scaffolds. ImportError at Wave 0 → xfail; import resolution at Wave 2 (Plan 05-05) → natural xpass + Plan 05-06 marker removal.
- **data/eval/ directory tree established** as new sibling for Phase 8 ground-truth and Phase 10 eval reports. cases.jsonl placeholder satisfies the loader-test contract while the test_cases_loaded xfail strict=True correctly catches the < 5 records floor as the Wave 0 expected failure.
- **Phase 4's 96-pass baseline preserved** — `uv run pytest -ra -q` reports `96 passed, 6 skipped, 22 xfailed, 0 failed`. All 3 grep gates (check_index_wraps / check_adapter_wraps / check_ingest_wraps) still pass — Phase 5 added zero new SDK call sites.

## Task Commits

Each task was committed atomically:

1. **Task 0: Extend CLAUDE.md Phase 5 hard-gate paragraph by one sentence** — `8d98531` (docs)
2. **Task 1: Create the four pure-unit test scaffolds (RRF + null adapters + RetrievedChunk schema + factory)** — `7dcd866` (test)
3. **Task 2: Create the two integration test scaffolds (Retriever.search + canary) + the cases.jsonl placeholder** — `a3dd107` (test)

## Files Created/Modified

### Created (Task 1)
- `tests/test_rrf_fuse.py` — 4 xfail scaffolds for RET-01 (`test_rrf_fuse_known_score`, `test_rrf_skip_missing`, `test_rrf_one_based_ranks`, `test_rrf_k_constant`); Plan 05-03 ships `docintel_retrieve.fuse._rrf_fuse` + `RRF_K` and flips them.
- `tests/test_null_adapters.py` — 4 xfail scaffolds for D-08 ablation seam (`test_null_reranker_preserves_order`, `test_null_reranker_satisfies_protocol`, `test_null_bm25_empty`, `test_null_bm25_satisfies_protocol`); Plan 05-04 ships `docintel_retrieve.null_adapters` and flips them.
- `tests/test_retrieved_chunk_schema.py` — 4 xfail scaffolds for RET-04 + D-03 + CD-02 (`test_retrieved_chunk_required_fields`, `test_char_span_tuple`, `test_retrieved_chunk_forbids_extra`, `test_retrieved_chunk_is_frozen`); Plan 05-02 adds `RetrievedChunk` to `docintel_core.types` and flips them.
- `tests/test_make_retriever.py` — 2 xfail scaffolds for D-04 + CD-01 (`test_make_retriever_stub`, `test_chunk_map_eager_load`); Plan 05-05 ships the factory + Retriever and flips them.

### Created (Task 2)
- `tests/test_retriever_search.py` — 5 xfail scaffolds for RET-02 + CD-07 (`test_retriever_returns_top_k`, `test_assertion_quotes_claude_md`, `test_query_truncation_logs`, `test_telemetry_fields`, `test_zero_candidates`); Plan 05-05 ships Retriever.search and flips them. Uses `structlog.testing.capture_logs()` for log assertions (new pattern for Phase 5).
- `tests/test_reranker_canary.py` — 4 xfail scaffolds for RET-03 (`test_cases_loaded`, `test_reranker_canary_stub_mode`, `test_reranker_canary_real_mode`, `test_failure_message_quotes_claude_md`). Module-level `_REPO_ROOT`, `_CASES_PATH`, `_CLAUDE_MD_QUOTE` constants. `test_reranker_canary_real_mode` carries BOTH `@pytest.mark.real` (outer) AND `@pytest.mark.xfail` (inner). Plan 05-06 ships the canary driver and removes the xfails.
- `data/eval/canary/cases.jsonl` — Wave 0 placeholder JSONL with 1 record matching the D-13 6-field schema. Plan 05-06 replaces with curated >= 7 real cases per D-14 / D-17.

### Modified (Task 0)
- `CLAUDE.md` — Phase 5 hard-gate bullet (line 39) extended by one sentence: appended `This is the most common subtle failure mode and the canary exists specifically to catch it.` Single-character-precise edit: 1 insertion(+), 1 deletion(-). No other line in CLAUDE.md was changed.

## Verbatim `_CLAUDE_MD_QUOTE` value (so Wave 2 can grep against it)

The exact string constant defined at module-top in `tests/test_reranker_canary.py`:

```python
_CLAUDE_MD_QUOTE = (
    'Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation FIRST '
    "before suspecting hybrid retrieval, RRF, or chunk size. This is the most "
    'common subtle failure mode and the canary exists specifically to catch it."'
)
```

Concatenated: `Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation FIRST before suspecting hybrid retrieval, RRF, or chunk size. This is the most common subtle failure mode and the canary exists specifically to catch it."`

All three target substrings appear verbatim in CLAUDE.md (Task 0), in `_CLAUDE_MD_QUOTE` (Task 2), and (per Plan 05-05) will appear in `docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE`.

## Test-name-to-plan handoff (which Wave 1+ plan removes which xfail)

| Test file | Test functions | Wave / Plan that removes the xfail |
|-----------|----------------|------------------------------------|
| tests/test_retrieved_chunk_schema.py | test_retrieved_chunk_required_fields, test_char_span_tuple, test_retrieved_chunk_forbids_extra, test_retrieved_chunk_is_frozen | Wave 1 / **Plan 05-02** |
| tests/test_rrf_fuse.py | test_rrf_fuse_known_score, test_rrf_skip_missing, test_rrf_one_based_ranks, test_rrf_k_constant | Wave 1 / **Plan 05-03** |
| tests/test_null_adapters.py | test_null_reranker_preserves_order, test_null_reranker_satisfies_protocol, test_null_bm25_empty, test_null_bm25_satisfies_protocol | Wave 1 / **Plan 05-04** |
| tests/test_make_retriever.py | test_make_retriever_stub, test_chunk_map_eager_load | Wave 1 / **Plan 05-05** |
| tests/test_retriever_search.py | test_retriever_returns_top_k, test_assertion_quotes_claude_md, test_query_truncation_logs, test_telemetry_fields, test_zero_candidates | Wave 1 / **Plan 05-05** |
| tests/test_reranker_canary.py | test_cases_loaded, test_reranker_canary_stub_mode, test_failure_message_quotes_claude_md | Wave 2 / **Plan 05-06** |
| tests/test_reranker_canary.py | test_reranker_canary_real_mode (real-mode only) | Wave 2 / **Plan 05-06** (xfail removed); workflow_dispatch only per D-15 |

## Confirmation: all three target substrings now live in CLAUDE.md

Verified via grep at commit time:

```
$ grep -c "the canary exists specifically to catch it" CLAUDE.md
1
$ grep -c "BGE 512-token truncation FIRST" CLAUDE.md
1
$ grep -c "before suspecting hybrid retrieval, RRF, or chunk size" CLAUDE.md
1
$ grep -c "^- \*\*Phase 5 carries the reranker silent-truncation canary" CLAUDE.md
1
$ grep -E "look at BGE 512-token truncation FIRST.*before suspecting.*the canary exists specifically to catch it" CLAUDE.md | wc -l
       1
```

Single-line bullet, no duplicated bullet, no new heading added — verified by `git diff --stat CLAUDE.md` reporting `1 file changed, 1 insertion(+), 1 deletion(-)`.

## Decisions Made

- **Single-line `@pytest.mark.xfail` decorators.** Initial draft used multi-line Python-formatter-style decorators; the plan's verbatim verification grep `grep -B1 "^def test_" | grep -c "xfail(strict=True"` requires the decorator to fit on the line immediately preceding `def test_`. Reformatted all 23 decorators to single-line. Each line is < 200 chars and the test reason text is still readable.
- **Marker ordering on test_reranker_canary_real_mode.** Applied `@pytest.mark.real` as the OUTER decorator (closer to `def`) per PLAN.md's explicit constraint and per RESEARCH.md §9 Pattern A. pytest's marker-collection layer evaluates `-m "not real"` deselection at the strict-marker layer, so the outer marker is evaluated first; the inner xfail marker only fires when `-m real` actually selects the test. Verified by `uv run pytest tests/test_reranker_canary.py -m "not real"` deselecting exactly 1 test and `uv run pytest -m real --collect-only` finding exactly that test.
- **Anchored-hook xfail pattern.** `test_failure_message_quotes_claude_md` deliberately uses an IN-FUNCTION import of `_CLAUDE_MD_HARD_GATE` rather than a module-top import. Module-top would make the entire `tests/test_reranker_canary.py` file's collection fail at Wave 0 (ImportError at collection time, not test time). In-function import = ImportError at test time = expected xfail under `strict=True`. Pattern is wave-flip-safe: Plan 05-05 ships retriever.py with `_CLAUDE_MD_HARD_GATE`; the import resolves; the assertions run; the test xpasses; Plan 05-06 removes the xfail marker.
- **Wave 0 cases.jsonl ships 1 placeholder, not 5+.** Plan 05-01's plan-checker explicitly chose this: `test_cases_loaded` xfail (strict=True) at Wave 0 catches `len(cases) < 5` as the expected failure. Plan 05-06 lands the curated 7+ cases; the xfail flips to xpass and Plan 05-06 removes the marker in the same commit. This is the plan's intended "Wave 2 floor enforcement" semantic.

## Deviations from Plan

None — plan executed exactly as written.

The plan's 3 tasks were executed in order with verification gates passing after each task. Single-character precision on the CLAUDE.md edit (Task 0). All 23 test scaffold function names match 05-VALIDATION.md verbatim. The `_CLAUDE_MD_QUOTE` constant contains all three required substrings verbatim. The anchored in-function import hook is correctly placed inside `test_failure_message_quotes_claude_md` per WARNING 4 in success_criteria.

## Issues Encountered

- **Transient bm25_store test flake during full-suite run.** First `uv run pytest -ra -q` invocation reported `2 failed` in `tests/test_bm25_store.py` (`test_chunk_ids_aligned_with_rows`, `test_bm25_artifacts_present` — both FileNotFoundError / AssertionError on missing `data/indices/` artifacts). Investigated: re-running the suite reported `96 passed, 0 failed, 22 xfailed`. The two tests pass standalone (`uv run pytest tests/test_bm25_store.py` → 2 passed). Root cause: the worktree spawned with an empty `data/indices/` tree; the first full-suite run was racing the artifact-creation tests (`test_index_build.py`) against the artifact-consumer tests (`test_bm25_store.py`). After Phase 4's `test_index_build.py` ran once and created the artifacts, the suite went green. Confirmed Plan 05-01's changes were NOT the cause: at the base commit `de4ba0b` (pre-Plan-05-01) the same `test_bm25_store.py` also passes standalone. This is a pre-existing test-suite-state issue tracked for Phase 4 follow-up if it recurs in CI; out-of-scope for Plan 05-01.

## User Setup Required

None — no external service configuration required. All scaffolds are pure pytest fixtures + xfail markers; no API keys, no environment variables, no manual deployment.

## Self-Check

Verified at SUMMARY write time:

1. **CLAUDE.md substrings present:**
   - `grep -c "the canary exists specifically to catch it" CLAUDE.md` → `1` ✓
   - `grep -c "BGE 512-token truncation FIRST" CLAUDE.md` → `1` ✓
   - `grep -c "before suspecting hybrid retrieval, RRF, or chunk size" CLAUDE.md` → `1` ✓
2. **All 7 created files exist on disk:**
   - `tests/test_rrf_fuse.py` ✓ · `tests/test_null_adapters.py` ✓ · `tests/test_retrieved_chunk_schema.py` ✓ · `tests/test_make_retriever.py` ✓
   - `tests/test_retriever_search.py` ✓ · `tests/test_reranker_canary.py` ✓
   - `data/eval/canary/cases.jsonl` ✓
3. **All 3 commits exist in git:**
   - `8d98531` (Task 0) ✓ · `7dcd866` (Task 1) ✓ · `a3dd107` (Task 2) ✓
4. **Test counts:**
   - 14 xfailed in unit-only suite (`tests/test_{rrf_fuse,null_adapters,retrieved_chunk_schema,make_retriever}.py`) ✓
   - 8 xfailed + 1 deselected in integration-only suite under `-m "not real"` (`tests/test_{retriever_search,reranker_canary}.py`) ✓
   - 22 xfailed + 1 deselected in full Phase 5 quick suite under `-m "not real"` ✓
   - 0 failed in full project suite under `-ra -q` (96 passed, 6 skipped, 22 xfailed) ✓
5. **No module-top `docintel_retrieve` imports across all 6 new test files:**
   - `grep -E "^(from|import) docintel_retrieve" tests/test_{rrf_fuse,null_adapters,retrieved_chunk_schema,make_retriever,retriever_search,reranker_canary}.py | wc -l` → `0` ✓
6. **Anchored hook in test_failure_message_quotes_claude_md:**
   - `grep -F "from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE" tests/test_reranker_canary.py` → 1 match (in-function) ✓

## Self-Check: PASSED

## Threat Flags

None — Plan 05-01 added only test scaffolds (no executable production code), one CLAUDE.md sentence edit, and one committed JSONL data fixture with a placeholder record. No new network endpoints, no new auth paths, no new file-access patterns at trust boundaries, no schema changes outside of D-03's `RetrievedChunk` (which is scaffolded for Plan 05-02, not landed here). The threat-model entries T-5-V5-01-W0, T-5-V5-02-W0, T-5-V5-03-source-drift in 05-01-PLAN.md `<threat_model>` are mitigated by this plan's deliverables:
- T-5-V5-01-W0 (CLAUDE.md ↔ source-of-truth drift): mitigated by Task 0 single-character alignment + `_CLAUDE_MD_QUOTE` constant in test_reranker_canary.py.
- T-5-V5-02-W0 (cases.jsonl placeholder): accepted with grep-visible `PLACEHOLDER` text in the question field + the test_cases_loaded xfail strict=True that catches `len(cases) < 5` as expected failure at Wave 0.
- T-5-V5-03-source-drift: mitigated by the doubled-defense grep-asserts in test_failure_message_quotes_claude_md (when Plan 05-06 removes the xfail, drift across any of the 5 sources fires CI red).

## Next Plan Readiness

- **Plan 05-02 (RetrievedChunk Pydantic model)** — ready. Will flip 4 xfails in `tests/test_retrieved_chunk_schema.py`.
- **Plan 05-03 (RRF helper)** — ready. Will flip 4 xfails in `tests/test_rrf_fuse.py`.
- **Plan 05-04 (Null adapters)** — ready. Will flip 4 xfails in `tests/test_null_adapters.py`.
- **Plan 05-05 (Retriever + factory + `_CLAUDE_MD_HARD_GATE` module constant)** — ready. Will flip 7 xfails: 2 in `tests/test_make_retriever.py` + 5 in `tests/test_retriever_search.py`. Plan 05-05's `_CLAUDE_MD_HARD_GATE` constant MUST contain all three verbatim substrings so the anchored hook resolves at Wave 2.
- **Plan 05-06 (Canary driver + curated cases.jsonl)** — ready. Will replace the placeholder cases.jsonl with curated >= 7 cases and remove 4 xfails in `tests/test_reranker_canary.py`. Also removes the `@pytest.mark.xfail` from `test_reranker_canary_real_mode` (the `@pytest.mark.real` outer marker stays — it gates the test behind workflow_dispatch per D-15).
- **No blockers.** All 23 xfail-strict scaffolds are wave-flip-safe; pytest collection succeeds; the full project suite is green at 96-pass baseline + 22 new xfails.

---
*Phase: 05-retrieval-hybrid-rerank*
*Plan: 01*
*Completed: 2026-05-14*
