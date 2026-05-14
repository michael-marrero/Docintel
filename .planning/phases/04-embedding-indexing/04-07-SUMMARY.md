---
phase: 04-embedding-indexing
plan: 07
subsystem: testing
tags: [indexing, xfail-flip, phase-gate, final, lint-cleanup]
requires:
  - phase: 04-embedding-indexing/04-01
    provides: "Wave-0 test scaffolds (9 stub-mode + 1 real-mode) with xfail markers"
  - phase: 04-embedding-indexing/04-02
    provides: "IndexManifest schema; pyproject.toml real marker; scripts/check_index_wraps.sh; xfail markers"
  - phase: 04-embedding-indexing/04-04
    provides: "QdrantDenseStore + BgeSmallEnV15Embedder + Bm25sStore (real-mode adapters)"
  - phase: 04-embedding-indexing/04-05
    provides: "docintel-index build/verify/all CLI; corpus_identity_hash; _atomic_write_manifest; DOCINTEL_CHUNK_NAMESPACE pin"
  - phase: 04-embedding-indexing/04-06
    provides: "Makefile build-indices target; docker-compose qdrant service (profile real); CI stub-mode + workflow_dispatch jobs"
provides:
  - "Full phase gate verified: 0 xfailed, 0 xpassed across the Phase 4 test set"
  - "All 22 Phase-4 stub-mode tests run as hard assertions"
  - "3 real-mode tests gated only by `pytest -m real` (xfail removed, real preserved)"
  - "Decision Coverage Audit: every D-01..D-21 maps to at least one test or gate"
  - "Lint deferred items cleared — `ruff check packages/` + `black --check packages/ tests/` green"
  - "Phase 4 IDX-01..04 closed"
affects: [phase-05-retrieval-hybrid-rerank, phase-10-eval-harness]
tech-stack:
  added: []
  patterns:
    - "Final-wave xfail-removal: stale markers introduced as Wave-0 scaffold placeholders are stripped in the closing plan; xpasses convert to plain passes once impl has shipped (Phase 3 precedent — Plan 03-07 followed the same shape)"
    - "Module-level pytestmark single-marker reshape (`pytestmark = pytest.mark.real`): the simplest valid post-flip form when only one marker remains, matching Phase 3 convention"
    - "Lint cleanup folded into the final-flip wave: ruff + black green on every phase-gate commit, no opaque baseline drift carried into the next phase"
key-files:
  created:
    - ".planning/phases/04-embedding-indexing/04-07-SUMMARY.md"
  modified:
    - "tests/test_index_build.py — 4 xfail markers removed; try/except ImportError → hard import; black-reformatted"
    - "tests/test_bm25_store.py — 2 xfail markers removed; Rule 1 fix to row_count extraction (CSC indptr → scores['num_docs']); black-reformatted"
    - "tests/test_index_manifest.py — 3 xfail markers removed; try/except ImportError → hard import; black-reformatted"
    - "tests/test_index_gitignore.py — 1 xfail marker removed; black-reformatted"
    - "tests/test_index_byte_identity.py — 1 xfail marker removed"
    - "tests/test_qdrant_point_ids.py — 3 xfail markers removed; black-reformatted"
    - "tests/test_index_idempotency.py — 2 xfail markers removed; black-reformatted"
    - "tests/test_index_verify.py — 2 xfail markers removed; black-reformatted"
    - "tests/test_index_wraps_gate.py — 2 xfail markers removed"
    - "tests/test_index_build_real.py — pytestmark xfail element removed; real marker preserved; module docstring updated; black-reformatted"
    - "tests/test_index_stores.py — black-reformatted only"
    - "packages/docintel-core/src/docintel_core/adapters/real/bm25s_store.py — ruff F401 + black"
    - "packages/docintel-core/src/docintel_core/adapters/real/numpy_dense.py — black"
    - "packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py — black"
    - "packages/docintel-core/src/docintel_core/config.py — black"
    - "packages/docintel-index/src/docintel_index/build.py — ruff I001 + RUF001 ambiguous ×→x + black"
    - "packages/docintel-index/src/docintel_index/manifest.py — ruff I001 + RUF002 ambiguous ×→x + black"
    - "packages/docintel-index/src/docintel_index/verify.py — ruff I001 + black"
key-decisions:
  - "[Rule 1 fix] Corrected the bm25s row-count extraction in test_chunk_ids_aligned_with_rows from `len(indptr) - 1` (which equals the vocab size in bm25s 0.3.9's CSC layout) to `retriever.scores['num_docs']` (the canonical doc count). The IDX-02 contract is unchanged; only the bm25s 0.3.9 API call is corrected. Without this fix Plan 04-07 Task 1 acceptance would fail (the test was xfailed because of this bug; stripping the marker without fixing the bug would convert it to a hard failure)."
  - "[Plan option (a)] Reshaped `pytestmark` to the single-marker form `pytestmark = pytest.mark.real` rather than the single-element list `pytestmark = [pytest.mark.real]`. Matches Phase 3 precedent and reads cleaner — no list semantics needed when only one marker remains."
  - "[Scope] Folded the Plan 04-06 deferred-items cleanup (8 ruff + 14 black) into Plan 04-07 as a separate commit. The plan_context explicitly listed this as in-scope for the final gate; doing it here means Phase 4 ships with green lint CI on every commit rather than carrying baseline drift into Phase 5."
  - "[Strict acceptance] Updated module docstring narratives in every flipped file to remove the prior `intentionally @pytest.mark.xfail(strict=False)` wording. Without this, the literal-string acceptance criterion `grep -rn '@pytest.mark.xfail' tests/test_index_*.py | wc -l` would have returned 6 (docstring matches) instead of 0. Functionally identical state; acceptance criterion now strictly satisfied."
patterns-established:
  - "Phase 4 final-wave structure: Task 1 strips per-test markers across the stub-mode files + applies any Rule-1 fixes uncovered by the flip; Task 2 reshapes the module-level pytestmark on the real-mode file + runs the closing phase gate. Mirrors Phase 3 Plan 03-07."
  - "Deferred-items.md cleanup is a deliberate sub-step of the final flip wave (not a separate hygiene plan)."
requirements-completed: [IDX-01, IDX-02, IDX-03, IDX-04]
metrics:
  duration_minutes: 14
  tasks_completed: 2
  files_modified: 18  # 10 test files + 7 package source files + 1 SUMMARY.md (next commit)
  commit_count: 3  # Task 1 + lint cleanup + Task 2
  completed_date: 2026-05-14
---

# Phase 4 Plan 07: Final Wave — xfail-marker removal + closing phase gate

**Stripped every `@pytest.mark.xfail(strict=False, ...)` marker introduced by Plans 04-01/04-02 across 10 Wave-0 test files, fixed one Rule-1 bug in test_bm25_store.py uncovered by the flip, cleared the Plan-04-06 deferred ruff + black items, and ran the closing 10-step phase gate clean. Phase 4 (embedding-indexing) closes IDX-01..04 with full D-01..D-21 decision coverage.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-14T08:50:04Z
- **Completed:** 2026-05-14T09:04:39Z
- **Tasks:** 2 (per the plan; +1 sub-commit for the deferred-items cleanup)
- **Files modified:** 18 (10 test files + 7 package source files + this SUMMARY.md)
- **Commits:** 3

## Accomplishments

- 22 stub-mode Phase 4 tests now run as hard assertions (was: 4 passing + 2 xfailed + 18 xpassed at base)
- 3 real-mode integration tests gated only by `pytest -m real` (xfail dropped; real marker preserved)
- Full project test suite: 96 passed, 5 skipped, 0 xfailed, 0 xpassed, 0 errors
- Phase 4 lint CI step (FND-09) green: ruff + black both clean on the new package + adapter sources
- All 10 phase-gate verification commands green — Phase 4 closes IDX-01..04

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove xfail markers from 9 Wave-0 test files** — `077db5a` (test)
2. **Sub-commit: Clear ruff + black deferred items from Plans 04-04/04-05** — `6257914` (chore)
3. **Task 2: Remove xfail from test_index_build_real.py; real marker stays** — `f748373` (test)

**Plan metadata:** _(pending — this SUMMARY.md commit will be the final one in this plan)_

## Stub-mode xfail-removal inventory

| File | Markers removed | Tests now passing | Notes |
|------|-----------------|-------------------|-------|
| tests/test_index_build.py | 4 | 4 | try/except ImportError → hard `from docintel_index.build import corpus_identity_hash` at module top |
| tests/test_bm25_store.py | 2 | 2 | **Rule 1 fix:** row_count = `len(indptr) - 1` → `retriever.scores["num_docs"]` (see Deviations) |
| tests/test_index_manifest.py | 3 | 3 | try/except ImportError → hard `from docintel_index.manifest import _atomic_write_manifest` |
| tests/test_index_gitignore.py | 1 | 1 | — |
| tests/test_index_byte_identity.py | 1 | 1 | `import pytest` preserved per plan acceptance though unused |
| tests/test_qdrant_point_ids.py | 3 | 3 | namespace literal cross-pin verified against `qdrant_dense.py` |
| tests/test_index_idempotency.py | 2 | 2 | `pytest.importorskip("docintel_index")` retained (no-op now) |
| tests/test_index_verify.py | 2 | 2 | `pytest.importorskip("docintel_index")` retained (no-op now) |
| tests/test_index_wraps_gate.py | 2 | 2 | `import pytest` preserved per plan acceptance though unused |
| **Total stub-mode** | **20** | **20** | |

## Real-mode test inventory

`tests/test_index_build_real.py` — landed by Plan 04-01 Task 3 as a Wave-0 scaffold with `pytestmark = [pytest.mark.real, pytest.mark.xfail(...)]`. Plan 04-07 Task 2 reshapes it to the single-marker form:

```python
pytestmark = pytest.mark.real
```

Three real-mode tests (collected only under `pytest -m real`):

- `test_qdrant_collection_created` — asserts the Qdrant collection + manifest after a real-mode build
- `test_qdrant_verify_clean` — asserts `docintel-index verify` exits 0 on the clean real-mode build
- `test_real_mode_embedder_is_bge` — asserts MANIFEST records `bge-small-en-v1.5` identity (D-04 BGE adapter)

Each test body carries an explicit `os.environ.get("DOCINTEL_LLM_PROVIDER") != "real"` skip guard so accidental invocation in stub-mode is a no-op. Plan 04-06's `real-index-build` workflow_dispatch CI job is the only execution path.

Default suite collection picks up the file (no `-m 'not real'` in pyproject addopts), but each test SKIPs on the env-var guard — functionally equivalent to deselection for the safety property the plan cares about (these tests cannot fail by default).

## Final phase-gate verification (10/10 GREEN)

| # | Command | Exit | Result |
|---|---------|------|--------|
| 1 | `uv run pytest -ra -q` | 0 | 96 passed, 5 skipped, 0 xfailed, 0 xpassed, 0 errors |
| 2 | `bash scripts/check_index_wraps.sh` | 0 | OK: all real adapter files with qdrant_client calls have tenacity imports |
| 3 | `bash scripts/check_ingest_wraps.sh` | 0 | OK: Phase 3 gate still green |
| 4 | `bash scripts/check_adapter_wraps.sh` | 0 | OK: Phase 2 gate still green |
| 5 | `uv run docintel-index verify` | 0 | `index_verify_clean` (chunk_count=6053, dense_backend=numpy, bm25_vocab_size=7520) |
| 6 | `uv lock --check` | 0 | Resolved 120 packages |
| 7 | `uv run mypy --strict packages/*/src` | 0 | Success: no issues found in 43 source files |
| 8 | `make build-indices` | 0 | `index_build_skipped_unchanged_corpus` → `index_verify_clean` → `all_complete` (idempotent skip path) |
| 9 | `make help` lists `build-indices`; does NOT list obsolete `ingest` | — | PASS (`build-indices` present; `ingest` placeholder absent — Plan 04-06 deletion preserved) |
| 10 | `docker-compose.yml` qdrant gated by `profiles: ['real']` (no `depends_on` link) | — | PASS — structural YAML check (`grep -c "profiles: \['real'\]" docker-compose.yml` = 1; `grep -c 'depends_on: \[qdrant\]'` = 0). Docker CLI unavailable in executor sandbox; Plan 04-06 documented the same fallback. |

Also clean: `uv run ruff check packages/` = All checks passed; `uv run black --check packages/ tests/` = 73 files would be left unchanged.

## Decision Coverage Audit (D-01..D-21)

Every Phase 4 decision is now provably covered by at least one test or gate:

| Decision | Mapping |
|----------|---------|
| D-01 tiered dense backend | `test_qdrant_point_ids.py` + `test_index_build.py::test_stub_dense_build_writes_npy` (stub) + `test_index_build_real.py::test_qdrant_collection_created` (real) |
| D-02 DenseStore Protocol | Import test in Plan 04-03's verify |
| D-03 make_index_stores factory | Import test in Plan 04-05 Task 1's verify |
| D-04 NumPyDenseStore layout | `test_stub_dense_build_writes_npy` |
| D-05 docker-compose qdrant service `profile real` | Plan 04-06 verification (compose YAML grep) |
| D-06 amended (uuid5 derivation, payload chunk_id) | `test_qdrant_point_ids.py::test_uuid5_deterministic` + `::test_namespace_pinned` |
| D-07 BM25 = bm25s pinned | `bm25s==0.3.9` in pyproject + `manifest.bm25.library_version` cross-check (`test_manifest_records_library_versions`) |
| D-08 BM25 tokenization | `bm25s_store.py` grep for `stopwords="en"` + stemmer (`PyStemmer`) |
| D-09 k1/b defaults | `bm25s_store.py` grep for `k1=1.5` + `b=0.75` |
| D-10 BM25 storage layout | `test_bm25_store.py::test_bm25_artifacts_present` |
| D-11 BM25 ranks-only | `BM25Store.query` Protocol returns `list[tuple[str, int, float]]` (rank is the int) |
| D-12 idempotency skip-if-unchanged | `test_index_idempotency.py::test_skip_unchanged_corpus` |
| D-13 single MANIFEST.json schema | `test_index_manifest.py::test_manifest_required_fields` |
| D-14 verify CLI subcommand | `test_index_verify.py::test_verify_clean_build` + `::test_verify_detects_tampered_npy` |
| D-15 docintel-index package layout | `packages/docintel-index/` exists with correct module tree |
| D-16 CLI verbs build/verify/all | `cli.py` grep for `sub.add_parser` |
| D-17 Settings amendment | `tests/test_config.py`-style smoke in Plan 04-02 verify |
| D-18 uv.lock regen | `uv lock --check` exits 0 (verified in Task 2 phase gate) |
| D-19 Makefile build-indices | Plan 04-06 Task 1 verification + Task 2 phase-gate `make build-indices` exits 0 |
| D-20 stub-mode CI on every PR + real-mode workflow_dispatch | Plan 04-06 Task 2 verification (CI yaml grep) |
| D-21 `scripts/check_index_wraps.sh` CI grep gate | `test_index_wraps_gate.py::test_grep_gate_catches_unwrapped` + `::test_grep_gate_passes_wrapped` + Plan 04-06 CI step |

**Every D-01..D-21 has at least one test or gate. Phase 4 is complete.**

## Files Created/Modified

**Created (this plan):**
- `.planning/phases/04-embedding-indexing/04-07-SUMMARY.md` — this file

**Modified (Task 1 — xfail removal across 9 stub-mode files):**
- `tests/test_index_build.py` (4 markers + 1 try/except → hard import + docstring refresh)
- `tests/test_bm25_store.py` (2 markers + Rule 1 num_docs fix + docstring refresh)
- `tests/test_index_manifest.py` (3 markers + 1 try/except → hard import + docstring refresh)
- `tests/test_index_gitignore.py` (1 marker + docstring refresh)
- `tests/test_index_byte_identity.py` (1 marker + docstring refresh)
- `tests/test_qdrant_point_ids.py` (3 markers + docstring refresh)
- `tests/test_index_idempotency.py` (2 markers + docstring refresh)
- `tests/test_index_verify.py` (2 markers + docstring refresh)
- `tests/test_index_wraps_gate.py` (2 markers + docstring refresh)

**Modified (sub-commit — lint cleanup, deferred from Plans 04-04/04-05):**
- `packages/docintel-core/src/docintel_core/adapters/real/bm25s_store.py` (ruff F401 + black)
- `packages/docintel-core/src/docintel_core/adapters/real/numpy_dense.py` (black)
- `packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py` (black)
- `packages/docintel-core/src/docintel_core/config.py` (black)
- `packages/docintel-index/src/docintel_index/build.py` (ruff I001 + RUF001 ASCII normalisation + black)
- `packages/docintel-index/src/docintel_index/manifest.py` (ruff I001 + RUF002 ASCII normalisation + black)
- `packages/docintel-index/src/docintel_index/verify.py` (ruff I001 + black)
- `tests/test_index_stores.py` (black only — no xfail markers in this file)

**Modified (Task 2 — real-mode pytestmark reshape):**
- `tests/test_index_build_real.py` (pytestmark single-marker reshape + docstring refresh)

## Decisions Made

- **Rule 1 fix to bm25s row-count extraction (test_bm25_store.py):** The original Plan 04-02 test used `row_count = len(retriever.scores["indptr"]) - 1` to derive the bm25s document count. In bm25s 0.3.9's CSC layout (matrix indexed by token: rows=docs, cols=vocab), `len(indptr) - 1` equals the *vocab size*, not the doc count. The canonical doc count is `retriever.scores["num_docs"]`. Without the fix, removing the xfail marker would have converted an XPASS into a HARD FAIL (the test had been xfailing because of this exact discrepancy — `len(chunk_ids)=6053` vs `len(indptr)-1=7519`). The IDX-02 test contract is preserved verbatim; only the bm25s API call shape is corrected.

- **Single-marker pytestmark reshape on test_index_build_real.py:** Both `pytestmark = pytest.mark.real` and `pytestmark = [pytest.mark.real]` are valid post-flip shapes per the plan. Single-marker form chosen for readability and Phase 3 precedent — no list semantics are needed when only one marker remains.

- **Lint cleanup folded into Plan 04-07 as a discrete sub-commit:** Plan 04-07's `plan_context` explicitly listed the 8 ruff + 14 black baseline issues as in-scope for the final gate. Doing the cleanup HERE (rather than punting to Phase 5) ensures Phase 4 ships with green lint CI on every commit. Committed separately from the Task-1 and Task-2 test edits to keep semantic clarity in `git log`.

- **Module docstrings updated to match post-flip state:** The plan's acceptance criterion `grep -rn '@pytest.mark.xfail' tests/test_index_*.py | wc -l returns 0` is literal — it matches docstring narratives too. Without updating the prior `intentionally @pytest.mark.xfail(strict=False) until ...` wording, the count would have been 6 (docstring lines across 6 files) instead of 0. Functionally identical state; acceptance criterion now strictly satisfied. Docstrings now describe the post-flip reality (`Plan 04-07 Task 1 removed the former xfail markers so these assertions now run as hard tests`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Wrong bm25s API call for row count in test_chunk_ids_aligned_with_rows**

- **Found during:** Task 1 (Removing xfail from `tests/test_bm25_store.py`)
- **Issue:** The Plan 04-02 scaffold computed `row_count = len(retriever.scores["indptr"]) - 1` and asserted `len(chunk_ids) == row_count`. In bm25s 0.3.9's CSC layout (matrix indexed by token: rows=docs, cols=vocab), `len(indptr) - 1` equals the **vocab size** (7519), not the doc count (6053). The test was xfailing on its own assertion because of this — stripping the xfail marker without the fix would convert the XFAIL into a HARD FAIL.
- **Fix:** Replaced the indptr-based row-count extraction with the canonical `num_docs = int(retriever.scores["num_docs"])`. The IDX-02 test contract is unchanged — same assertion structure, same Pitfall 2 rationale, same `len(chunk_ids) == <row_count>` semantics — only the bm25s 0.3.9 API call is corrected. Updated the inline comment to document the bm25s 0.3.9 CSC layout and added a pointer to this deviation log.
- **Verification:** `uv run pytest tests/test_bm25_store.py::test_chunk_ids_aligned_with_rows -ra -q` → 1 passed (was: 1 xfailed pre-fix). Full slice (`tests/test_bm25_store.py`) → 2 passed.
- **Files modified:** `tests/test_bm25_store.py`
- **Commit:** `077db5a` (Task 1 commit — folded into the xfail-removal commit because the fix is what makes the marker removal possible at all).

**2. [Rule 2 — Critical functionality] Module-docstring text update to satisfy the literal grep acceptance criterion**

- **Found during:** Task 1 verification (`grep -rn '@pytest.mark.xfail' tests/test_index_*.py tests/test_bm25_store.py tests/test_qdrant_point_ids.py | wc -l` returned 6 — all docstring matches)
- **Issue:** The plan's acceptance criterion is literal: `grep -rn '@pytest.mark.xfail' ... | wc -l returns 0`. Six docstring lines across six files said `intentionally @pytest.mark.xfail(strict=False) until ...` — once the markers ship removal, this language is stale and the criterion fails.
- **Fix:** Rewrote each of the 6 stale docstring narratives to describe the post-flip reality. Same intent (file is a Wave-0 scaffold); updated tense (markers WERE removed; tests RUN as hard tests). The implementing-plan references (04-04, 04-05) are preserved for history.
- **Verification:** `grep -rn '@pytest.mark.xfail' tests/test_index_build.py tests/test_bm25_store.py tests/test_index_manifest.py tests/test_index_gitignore.py tests/test_index_byte_identity.py tests/test_qdrant_point_ids.py tests/test_index_idempotency.py tests/test_index_verify.py tests/test_index_wraps_gate.py | wc -l` → 0.
- **Files modified:** All 9 stub-mode test files (Task 1) + `tests/test_index_build_real.py` (Task 2).
- **Commit:** `077db5a` (Task 1) + `f748373` (Task 2).

**3. [Rule 2 — Missing critical functionality] Pre-existing lint baseline cleared as part of the phase-closing gate**

- **Found during:** Plan 04-07 plan_context pre-flight (the executor was explicitly told to pick this up; Plan 04-06's deferred-items.md was the originating record)
- **Issue:** 8 ruff errors (5 auto-fixable I001/F401 + 3 RUF001/RUF002 ambiguous `×` MULTIPLICATION SIGN) and 14 black-reformat files were left over from Plans 04-04 + 04-05. Phase 4's CI lint step (FND-09) would have stayed red on every PR until cleared.
- **Fix:** Ran `uv run ruff check --fix packages/` (5 auto-fixed; 3 ambiguous-Unicode replaced manually with ASCII `x` / `~=` in prose docstrings) + `uv run black packages/ tests/` (14 files reformatted). No behavioural changes — pure formatter / lint-organisation.
- **Verification:** `uv run ruff check packages/` → All checks passed; `uv run black --check packages/ tests/` → 73 files would be left unchanged; full pytest suite still 96 passed / 5 skipped.
- **Files modified:** 7 source files under `packages/docintel-{core,index}/` + 9 test files under `tests/` (overlaps with Task 1 / Task 2 test files for the black-only style changes).
- **Commit:** `6257914` (committed separately from Task 1 / Task 2 to keep semantic clarity in `git log`).

---

**Total deviations:** 3 auto-fixed (1 Rule-1 bug, 2 Rule-2 critical-functionality).
**Impact on plan:** All three deviations are necessary to satisfy the plan's own acceptance criteria. The Rule-1 fix unblocks Task 1's xfail removal; the docstring-text fix satisfies the literal-grep criterion; the lint cleanup is explicitly in-scope per the plan_context. No scope creep.

### Auth gates encountered

None.

## Issues Encountered

- **Initial `uv run pytest` failed at conftest import:** The worktree's venv was empty on spawn — required `uv sync --all-packages --frozen` before any pytest invocation. Pattern matches every prior Phase 4 wave; the worktree venv is provisioned lazily.
- **Docker CLI unavailable in executor sandbox:** Phase-gate item 10 (`docker compose config` to confirm qdrant is gated by `profile real`) substitutes a YAML structural check — same approach Plan 04-06 used.

## Threat surface scan

No new threat surface introduced. The xfail-removal is one-way (T-4-V5-01 disposition `mitigate`): once flipped, any future implementation regression becomes a hard test failure visible in CI rather than a silent xfail-strict-false flip. The real-mode gating discipline (T-4-V5-02) is preserved verbatim — `pytest.mark.real` is the structural gate; the workflow_dispatch CI job is the only execution path. The three CI grep gates (adapter, ingest, index) all remain green (T-4-V5-03 `mitigate`).

No `threat_flag` entries to report.

## Self-Check

**Created files exist:**
- `.planning/phases/04-embedding-indexing/04-07-SUMMARY.md` — FOUND (this file)

**Commits exist on this worktree branch:**
- `077db5a` (Task 1 — xfail removal across 9 stub-mode test files) — FOUND
- `6257914` (sub-commit — clear ruff + black deferred items) — FOUND
- `f748373` (Task 2 — xfail removal from test_index_build_real.py; real marker stays) — FOUND

**Modified files committed:**
- 10 test files under `tests/` — committed across 077db5a + 6257914 + f748373
- 7 package source files under `packages/docintel-{core,index}/` — committed in 6257914

## Self-Check: PASSED

## Next Phase Readiness

Phase 5 (retrieval-hybrid-rerank) is unblocked. The Plan 04-05 `DenseStore` + `BM25Store` Protocols + `make_index_stores` factory are the consumption surface; the MANIFEST.json embedder/dense/bm25 blocks are the source of truth for Phase 10's eval-report manifest header (`embedder.name`, `dense.backend`, `bm25.library_version`).

Known cross-cutting follow-ups (not blockers for Phase 5):
- `tests/test_index_stores.py` has two `B007 Loop control variable 'chunk_id' not used within loop body` ruff warnings — `tests/` isn't in the CI `ruff check` allowlist (only `packages/` is), so these don't break CI. Drop-in rename to `_chunk_id` if Phase 5 wants the slate clean.
- `import pytest` is now technically unused in 4 of the flipped test files (`test_index_build.py`, `test_index_gitignore.py`, `test_index_byte_identity.py`, `test_index_wraps_gate.py`) — preserved per plan acceptance ("every file still has at least one import pytest line"). Same caveat as above (tests/ not enforced by CI).

---
*Phase: 04-embedding-indexing*
*Completed: 2026-05-14*
