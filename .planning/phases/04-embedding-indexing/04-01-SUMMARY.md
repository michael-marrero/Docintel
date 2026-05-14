---
phase: 04-embedding-indexing
plan: 01
subsystem: testing
tags: [pytest, xfail, tests-first, scaffold, indexing, bm25, numpy, qdrant, uuid5]

# Dependency graph
requires: []  # Wave 0 — no upstream
provides:
  - 7 xfail-marked stub-mode test files anchoring every later Plan 04-XX <verify> step on a real pytest command
  - 1 negative-case static fixture for the index-wrap grep gate (Plan 04-06 consumes)
  - Module-level pytestmark pattern (real + xfail) for tests/test_index_build_real.py — Plan 04-07 Task 2 removes only the xfail element
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07]

# Tech tracking
tech-stack:
  added: []  # Pure test scaffolds — no new runtime deps
  patterns:
    - "Module-level pytestmark = [pytest.mark.real, pytest.mark.xfail(strict=False, ...)] keeps two markers in sync; Plan 04-07 Task 2 removes only the xfail element"
    - "pytest.importorskip / try-except ImportError + pytest.xfail wrappers around symbols from later plans so test collection never errors before implementation lands"
    - "Static .py fixture under tests/fixtures/<gate-name>/ (NOT .example) for grep-gate negative cases — pytest does not collect (filename doesn't match test_*.py)"

key-files:
  created:
    - tests/test_index_build.py
    - tests/test_bm25_store.py
    - tests/test_index_gitignore.py
    - tests/test_index_manifest.py
    - tests/test_index_byte_identity.py
    - tests/test_qdrant_point_ids.py
    - tests/test_index_build_real.py
    - tests/fixtures/missing_tenacity/qdrant_fake.py
  modified: []

key-decisions:
  - "Module-level pytestmark for the real-mode test file (BOTH real + xfail) — Plan 04-07 Task 2 removes only the xfail element so the real marker stays and the file remains gated by `pytest -m real`"
  - "Static fixture (.py, NOT .example) for grep-gate negative case — Plan 04-06's check_index_wraps.sh needs a real .py file to grep against"

patterns-established:
  - "Pattern: every later plan's <verify> step grounds on `pytest tests/test_index_*.py -ra -q` rather than ad-hoc assertions — this Wave 0 establishes the Nyquist sampling surface"
  - "Pattern: xfail(strict=False) for tests-first scaffolds prevents iterative-build-up false-positives on xpassed (numpy/gitignore-rule tests will xpass today; bm25s/qdrant tests will xfail until Plans 04-04/04-05 land)"

requirements-completed: [IDX-01, IDX-02, IDX-03, IDX-04]

# Metrics
duration: 9min
completed: 2026-05-14
---

# Phase 04 Plan 01: Wave 0 test-scaffolding Summary

**7 xfail-marked pytest scaffolds + 1 grep-gate negative fixture anchoring IDX-01/02/03/04, Pitfall 3 (np.save), Pattern 3 (uuid5), Pattern 4 (bm25s layout), Pitfall 8 (atomic write), and Pitfall 9 (corpus-hash strip).**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-14T07:02:29Z
- **Completed:** 2026-05-14T07:11:59Z
- **Tasks:** 3
- **Files modified:** 8 (7 test files + 1 fixture)

## Accomplishments

- Landed `tests/test_index_build.py` (4 tests — IDX-01 stub build, IDX-02 cross-store chunk_id, Pitfall 9 corpus_identity_hash, Pitfall 4 empty-filing skip)
- Landed `tests/test_bm25_store.py` (2 tests — IDX-02 chunk_id sidecar alignment, Pattern 4 canonical 5-file bm25s save layout)
- Landed `tests/test_index_gitignore.py` (1 test — IDX-04 source check + behavioral `git check-ignore` umbrella rule)
- Landed `tests/test_index_manifest.py` (3 tests — IDX-03 schema, Pitfall 6 library_version recording, Pitfall 8 atomic-write try/finally cleanup)
- Landed `tests/test_index_byte_identity.py` (1 test — Pitfall 3 np.save byte-determinism canary with verbatim RESEARCH test vector)
- Landed `tests/test_qdrant_point_ids.py` (3 tests — Pattern 3 uuid5 determinism, collision-resistance, DOCINTEL_CHUNK_NAMESPACE pin)
- Landed `tests/test_index_build_real.py` (3 tests — IDX-01 real-mode Qdrant collection + verify + BGE embedder identity; module-level `pytestmark = [pytest.mark.real, pytest.mark.xfail(strict=False, ...)]`)
- Landed `tests/fixtures/missing_tenacity/qdrant_fake.py` (static fixture for Plan 04-06 grep gate — imports qdrant_client + calls client.upsert WITHOUT any retry import)

## Task Commits

Each task was committed atomically:

1. **Task 1: tests/test_index_build.py + test_bm25_store.py + test_index_gitignore.py** — `b3884f3` (test)
2. **Task 2: tests/test_index_manifest.py + test_index_byte_identity.py + test_qdrant_point_ids.py + missing_tenacity/qdrant_fake.py** — `275faac` (test)
3. **Task 3: tests/test_index_build_real.py** — `2347122` (test)

**Plan metadata:** _pending — commit appended next_ (docs: complete plan)

## Files Created/Modified

- `tests/test_index_build.py` — 4 xfail-marked subprocess-driven tests anchoring `uv run docintel-index build` (Plan 04-05) on IDX-01 / IDX-02 / Pitfall 9 / Pitfall 4
- `tests/test_bm25_store.py` — 2 xfail-marked tests anchoring `chunk_ids.json` row alignment + Pattern 4 file layout; uses `pytest.importorskip("bm25s")` for defensive collection
- `tests/test_index_gitignore.py` — 1 xfail-marked test asserting `data/indices/` gitignore via `.gitignore` source check AND `git check-ignore --no-index` behavioral check
- `tests/test_index_manifest.py` — 3 xfail-marked tests covering MANIFEST schema, `importlib.metadata.version("bm25s")` recording, and `_atomic_write_manifest` partial-failure cleanup (try/finally .tmp unlink)
- `tests/test_index_byte_identity.py` — 1 xfail-marked test with verbatim Pitfall 3 vector (`np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)`)
- `tests/test_qdrant_point_ids.py` — 3 xfail-marked tests for `chunk_id_to_point_id` determinism + collision-resistance + `DOCINTEL_CHUNK_NAMESPACE` pin; uses `pytest.importorskip("docintel_core.adapters.real.qdrant_dense")` defensively
- `tests/test_index_build_real.py` — 3 module-level-marked tests (`pytestmark = [pytest.mark.real, pytest.mark.xfail(strict=False, ...)]`) for real-mode Qdrant integration; env-var skip guards keep developers from accidental real-mode invocations
- `tests/fixtures/missing_tenacity/qdrant_fake.py` — static fixture; `from qdrant_client import QdrantClient` + `client.upsert(...)` with NO retry-library import; comment-block carefully avoids the literal `from tenacity import` pattern so the grep gate (Plan 04-06) correctly identifies this as un-wrapped

## Decisions Made

- **Module-level `pytestmark` list for real-mode file:** `pytestmark = [pytest.mark.real, pytest.mark.xfail(strict=False, reason=...)]` keeps the two markers in sync. Plan 04-07 Task 2 removes only the `pytest.mark.xfail` element — `pytest.mark.real` stays so the file remains gated by `pytest -m real` even after Wave 0 closes.
- **Static `.py` fixture (not `.example`):** The grep gate (Plan 04-06) needs a real `.py` source to scan. The `tests/fixtures/<gate>/` location keeps it out of pytest collection (filename doesn't match `test_*.py` and lives outside testpath collection scope).
- **`pytest.importorskip` / `try/except ImportError` wrappers:** Symbols from later plans (`bm25s`, `docintel_core.adapters.real.qdrant_dense`, `docintel_index.build.corpus_identity_hash`, `docintel_index.manifest._atomic_write_manifest`) are wrapped so test collection never errors before implementation lands. The runtime path produces SKIPPED (importorskip) or XFAIL (after the explicit `pytest.xfail` call) rather than ImportError.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed `from tenacity import` literal from qdrant_fake.py comments**
- **Found during:** Task 2 verify (acceptance criterion `grep -L 'from tenacity import' tests/fixtures/missing_tenacity/qdrant_fake.py`)
- **Issue:** Initial comment block at lines 6-9 contained the phrase `from tenacity import` as part of a sentence ("...without a corresponding \`from tenacity import\` line"). `grep -q 'from tenacity import'` matched this comment line, which would defeat Plan 04-06's grep gate — the gate would consider the file as "having tenacity import" and skip the negative-case assertion.
- **Fix:** Rewrote the comment to avoid the literal pattern. Comment now says "without a corresponding tenacity retry import" and "the retry import AND a qdrant call site" — no literal `from tenacity import` substring anywhere in the file.
- **Files modified:** tests/fixtures/missing_tenacity/qdrant_fake.py
- **Verification:** `grep -L 'from tenacity import' tests/fixtures/missing_tenacity/qdrant_fake.py` now lists the file (the `-L` flag returns files NOT containing the pattern — desired). `grep -q 'from qdrant_client import' tests/fixtures/missing_tenacity/qdrant_fake.py` still exits 0 (positive pattern preserved).
- **Committed in:** `275faac` (Task 2 commit — the fix was applied before the commit, so it's a single clean commit, not a separate fix commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix preserves the fixture's primary purpose (be the negative case for Plan 04-06's grep gate). No scope creep. The plan's behavior block explicitly specified that the fixture "does NOT import tenacity" — the comment fix enforces that contract.

## Issues Encountered

- **Transient `PytestUnknownMarkWarning` for `pytest.mark.real`:** Plan 04-02 (parallel Wave 1) registers the `real` marker in `pyproject.toml`. Until that merges, `pytest tests/test_index_build_real.py` emits a single `PytestUnknownMarkWarning`. The plan explicitly anticipated this transient state — `--strict-markers` in default `addopts` only errors when `-m unknown` filter is used at the CLI, NOT when an unregistered marker is applied to a test. Full project suite still exits 0 (no test failures). Plan 04-02 closes the gap.

## User Setup Required

None — pure test scaffolding, no external service configuration.

## Next Phase Readiness

- **Plan 04-02 (Wave 1 parallel)** lands `IndexManifest` Pydantic model + registers `real` pytest marker. Once merged, the unknown-mark warning disappears.
- **Plan 04-04 (Wave 2)** lands `docintel-index` CLI + `BGEEmbedder` + `QdrantDenseStore` + `chunk_id_to_point_id` / `DOCINTEL_CHUNK_NAMESPACE` exports. Three of the seven test files will flip from xfailed to xpassed.
- **Plan 04-05 (Wave 3)** lands `docintel_index.build` (corpus_identity_hash, _atomic_write_manifest, dense+bm25 build loops). The remaining stub-mode tests flip from xfailed to xpassed.
- **Plan 04-06 (Wave 4)** lands `scripts/check_index_wraps.sh` grep gate + `tests/test_index_wraps_gate.py` test that consumes `tests/fixtures/missing_tenacity/qdrant_fake.py` as the negative case. Also adds the `build-indices` CI job.
- **Plan 04-07 (Wave 5)** removes all `@pytest.mark.xfail` markers from these 7 files. For `tests/test_index_build_real.py`, Task 2 removes ONLY the `pytest.mark.xfail` element from `pytestmark` — the `pytest.mark.real` element stays so the file remains gated by `pytest -m real`.

## Plan Verification Results

Plan-level `<verification>` block (run at task 3 completion):

1. **6 stub-mode files combined** (`pytest tests/test_index_build.py tests/test_bm25_store.py tests/test_index_gitignore.py tests/test_index_manifest.py tests/test_index_byte_identity.py tests/test_qdrant_point_ids.py -ra -q`): **exit 0** — 8 xfailed + 2 xpassed + 4 skipped = 14 collected nodes (matches plan's expected 4+2+1+3+1+3). The xpasses (test_indices_dir_ignored, test_np_save_deterministic) are accepted because `strict=False`; gitignore rule already exists today and numpy IS byte-deterministic — both will flip to xfail-removed in Plan 04-07 once the surrounding implementation depends on them.
2. **Full project suite** (`pytest -ra -q`): **exit 0** — 66 passed (Phase 1/2/3 unchanged) + 9 skipped + 8 xfailed + 2 xpassed + 1 warning (PytestUnknownMarkWarning for `pytest.mark.real`; Plan 04-02 registers).
3. **Real-mode collect-only** (`pytest tests/test_index_build_real.py -m real --collect-only -q`): **3 tests collected** (matches plan).
4. **Fixture-correct check** (`test -f tests/fixtures/missing_tenacity/qdrant_fake.py && ! grep -q 'from tenacity import' tests/fixtures/missing_tenacity/qdrant_fake.py && echo fixture-correct`): **prints `fixture-correct`** — file exists AND lacks the literal `from tenacity import` pattern.

## Self-Check

Verified all created files exist on disk in the worktree:

- `tests/test_index_build.py` — FOUND
- `tests/test_bm25_store.py` — FOUND
- `tests/test_index_gitignore.py` — FOUND
- `tests/test_index_manifest.py` — FOUND
- `tests/test_index_byte_identity.py` — FOUND
- `tests/test_qdrant_point_ids.py` — FOUND
- `tests/test_index_build_real.py` — FOUND
- `tests/fixtures/missing_tenacity/qdrant_fake.py` — FOUND

Verified all 3 task commits exist in `git log`:

- `b3884f3` — FOUND (Task 1: test_index_build.py + test_bm25_store.py + test_index_gitignore.py)
- `275faac` — FOUND (Task 2: test_index_manifest.py + test_index_byte_identity.py + test_qdrant_point_ids.py + qdrant_fake.py)
- `2347122` — FOUND (Task 3: test_index_build_real.py)

## Self-Check: PASSED

---
*Phase: 04-embedding-indexing*
*Completed: 2026-05-14*
