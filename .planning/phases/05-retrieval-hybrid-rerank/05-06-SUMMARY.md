---
phase: 05-retrieval-hybrid-rerank
plan: 06
subsystem: retrieval
tags: [reranker-canary, structural-acceptance-gate, ret-03, claude-md-pitfall-6, real-mode-only, schema-only-stub-gate, workflow-dispatch, option-d-resolution]

# Dependency graph
requires:
  - phase: 02-adapters-protocols
    provides: AdapterBundle (Reranker), StubReranker + StubEmbedder (both backed by `_text_to_vector` hash — load-bearing for the Option D resolution)
  - phase: 03-corpus-ingestion
    provides: data/corpus/chunks/<TICKER>/FY<year>.jsonl (6,053 chunks across 15 tickers; 9 fully covered — AAPL/MSFT/NVDA/TSLA/JPM/V/PG/JNJ/HD)
  - phase: 04-embedding-indexing
    provides: IndexStoreBundle, MANIFEST.json (Pitfall 7 cardinality re-check)
  - phase: 05-retrieval-hybrid-rerank (Plan 05-01)
    provides: tests/test_reranker_canary.py scaffold (xfail-strict + _CLAUDE_MD_QUOTE + _CASES_PATH + _REPO_ROOT), data/eval/canary/cases.jsonl placeholder
  - phase: 05-retrieval-hybrid-rerank (Plan 05-04)
    provides: NullReranker (the dense-only ablation seam — D-08; used by the real-mode canary test)
  - phase: 05-retrieval-hybrid-rerank (Plan 05-05)
    provides: docintel_retrieve.retriever.Retriever + make_retriever(cfg) factory + _CLAUDE_MD_HARD_GATE module constant (the Pitfall 6 source of truth that this plan grep-asserts against)
provides:
  - "8 hand-curated canary cases committed to data/eval/canary/cases.jsonl (replacing Plan 05-01's placeholder)"
  - "Canary test driver tests/test_reranker_canary.py with 4 test functions per RESEARCH §9 Pattern A — schema-only stub-mode test (Option D) + real-mode strict-D-14 differential test (xfail-pending Plan 05-07 workflow_dispatch verification)"
  - "CI visibility step in default lint-and-test job — `Reranker canary (stub-mode acceptance gate) (RET-03)` — gives RET-03 its own green/red GitHub Actions box"
  - "Plan-05-06 amendment to CONTEXT.md D-14 + D-15 — stub-mode bite weakened to schema-only; strict differential bites in real mode only"
  - "Pitfall 6 doubled-defense — `test_failure_message_quotes_claude_md` asserts the three verbatim substrings on BOTH _CLAUDE_MD_QUOTE (test-local) AND _CLAUDE_MD_HARD_GATE (retriever module), with the import promoted from in-function to module-top"
affects: [phase-05-retrieval-hybrid-rerank-plan-07, phase-11-ablation-studies, phase-13-api-ui-polish, phase-14-v2-deferred]

# Tech tracking
tech-stack:
  added: []  # zero new SDK deps; pure composition of cases.jsonl + canary driver + CI yaml step
  patterns:
    - "Single-file dual-mode pytest driver (RESEARCH §9 Pattern A) — `test_reranker_canary_stub_mode` (no marker, runs on every PR) + `test_reranker_canary_real_mode` (@pytest.mark.real outer + @pytest.mark.xfail inner, deselected by default CI's `not real` selector)"
    - "Schema-only stub-mode fallback (Plan 05-06 Option D amendment) — when the structural differential cannot bite in stub mode, the stub-mode test asserts the JSONL artifact's well-formedness invariants instead, preserving CI green/red signal on every PR while moving the bite-point to workflow_dispatch"
    - "Real-mode dense-only ablation construction — `make_retriever(cfg)` for the rerank pipeline + `Retriever(bundle.model_copy(update={'reranker': NullReranker()}), stores, cfg)` for the dense-only baseline, with both retrievers sharing embedder + index stores (only the rerank stage differs); the same Phase 5 D-08 adapter-swap pattern Phase 11 will reuse"
    - "Pitfall 6 doubled-defense — verbatim CLAUDE.md hard-gate substrings grep-asserted on BOTH a test-local constant AND a retriever module constant (5 sources total kept in sync: CLAUDE.md, ROADMAP.md, CONTEXT.md D-16, _CLAUDE_MD_QUOTE, _CLAUDE_MD_HARD_GATE)"
    - "Visibility-step CI pattern — a named step that re-runs a test subset for green/red labelling purposes, riding atop the implicit collection of the same tests by the broader `uv run pytest -ra -q` step. Pattern analog: `.github/workflows/ci.yml` line 87 `Build indices (stub)` (Phase 4)"

key-files:
  created:
    - "data/eval/canary/cases.jsonl — 8 hand-curated JSONL records (1 per non-empty line); each record carries the seven schema fields case_id / question / gold_chunk_ids / ticker / fiscal_year / rationale / mode (mode=\"real\" on every record per Option D)"
    - ".planning/phases/05-retrieval-hybrid-rerank/05-CONTEXT.md — canonical Phase 5 decision register pinning D-13/D-14/D-15/D-16/D-17 + the inline 2026-05-14 amendment block (.planning/ is gitignored per commit_docs=false; this SUMMARY.md is the public-repo artifact)"
    - ".planning/phases/05-retrieval-hybrid-rerank/05-06-SUMMARY.md — this file (force-committed via `git add -f`)"
    - ".planning/phases/05-retrieval-hybrid-rerank/deferred-items.md — out-of-scope ruff/black issues in Plan 05-05's files (factory.py + retriever.py) + the stub-reranker discriminative-power redesign ticket (target Phase 11 or v2 / Phase 14)"
  modified:
    - "tests/test_reranker_canary.py — full rewrite of the 4 test functions per Option D: test_cases_loaded (xfail removed, schema gate), test_reranker_canary_stub_mode (xfail removed, weakened to schema-only assertion), test_failure_message_quotes_claude_md (already de-xfailed by Plan 05-05; _CLAUDE_MD_HARD_GATE import promoted to module-top), test_reranker_canary_real_mode (kept @pytest.mark.real + @pytest.mark.xfail(strict=True, reason=\"Plan 05-07 — real-mode verification under workflow_dispatch\") — Plan 05-07 closes it)"
    - ".github/workflows/ci.yml — one new named step `Reranker canary (stub-mode acceptance gate) (RET-03)` in the default lint-and-test job, positioned right after the existing `uv run pytest -ra -q` step. Comment block references CLAUDE.md + the verbatim BGE-512-token-truncation note (Pitfall 6 + D-16). NO changes to the real-index-build workflow_dispatch job (its existing `uv run pytest -m real -ra -q` step at line 286 auto-collects test_reranker_canary_real_mode per RESEARCH §10)."

key-decisions:
  - "Option D resolution (user-approved at the Plan 05-06 Task 1 curation checkpoint) — every case in cases.jsonl carries mode=\"real\"; stub-mode test weakened to schema-only assertion; strict D-14 differential bites in real-mode only (Plan 05-07 workflow_dispatch closes it). Deferred ticket: stub-reranker discriminative-power redesign (target Phase 11 or v2 / Phase 14)."
  - "Schema field amendment — the D-13 6-field schema is extended by a seventh `mode` field (values: \"real\", \"stub\", or null). Plan 05-06 Task 1 commits all 8 cases with mode=\"real\". Plan 05-06 Task 2's stub-mode test asserts the field exists AND `mode in {real, stub, None}`. The real-mode test filters cases by `mode in {real, None}` (stub-only cases would be skipped — none today)."
  - "Empirical finding driving Option D (from the prior executor agent-a4a902167f87681e0): the stub reranker is structurally incapable of beating stub dense-only because both stages use `_text_to_vector` from `adapters/stub/embedder.py` as their underlying scoring function. A 307-case brute-force exploration produced 0 rerank-only wins and 60 dense-only wins (with ~80% identical-top-3 across the two retrievers). The Phase 5 STRUCTURAL ACCEPTANCE GATE remains structural — it just bites in real mode rather than stub mode."
  - "Pitfall 6 doubled-defense survives the amendment — _CLAUDE_MD_HARD_GATE (retriever.py) still carries the verbatim CLAUDE.md hard-gate paragraph; _CLAUDE_MD_QUOTE (test-local) carries it too; the real-mode test's failure messages embed the verbatim quote + D-16 three-step debug order. The stub-mode test no longer runs the rerank-vs-dense-only differential, but `test_failure_message_quotes_claude_md` continues to grep-assert all three substrings against both constants on every PR."
  - "Promotion of the _CLAUDE_MD_HARD_GATE import from in-function to module top — Plan 05-01 Task 2 placed `from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE` INSIDE the test body as a Wave-0 xfail hook (the in-function ImportError made the strict-xfail genuinely fail until Plan 05-05 shipped retriever.py). Plan 05-06 Task 2 moves this import to the module-top imports block (line 97) now that retriever.py exists. Standard wave-flip pattern."
  - "Deferred ticket scope and acceptance bar — the stub-reranker discriminative-power redesign (target Phase 11 or v2 / Phase 14) must produce `rerank_top3_hits > dense_only_top3_hits AND rerank_top3_hits >= 5` against the existing cases.jsonl IN STUB MODE. Once achieved, test_reranker_canary_stub_mode can be promoted from schema-only back to the strict D-14 differential, and the case-level `mode` field can be relaxed."

# Metrics
metrics:
  start: 2026-05-14T20:05:00Z
  end: 2026-05-14T20:30:00Z
  duration: ~25 minutes (3 tasks committed atomically)
  completed: 2026-05-14
  tasks_completed: 3
  files_modified: 3  # cases.jsonl, test_reranker_canary.py, ci.yml
  files_created: 2  # 05-CONTEXT.md (gitignored), 05-06-SUMMARY.md (this file)
  pytest_passed: 121
  pytest_xfailed: 0
  pytest_deselected: 4  # real-mode tests (3 from index/qdrant + this plan's canary real-mode test)
  pytest_skipped: 2  # adapters real-key + gitleaks binary (both pre-existing)
  mypy_strict_source_files: 47
  mypy_strict_errors: 0
  ci_grep_gates_passing: 3  # check_index_wraps.sh + check_adapter_wraps.sh + check_ingest_wraps.sh
---

# Phase 5 Plan 05-06 — Reranker Canary Driver + Curated Cases + CI Visibility (RET-03)

**One-liner:** Wired Plan 05-01's xfail scaffolds into the load-bearing Phase 5 STRUCTURAL ACCEPTANCE GATE — 8 hand-curated cases against real SEC 10-K text, a 4-test driver with Option-D schema-only stub gate + real-mode strict-D-14 differential, and a named CI step that gives RET-03 its own green/red box in the GitHub Actions UI.

---

## Tasks completed

### Task 1 — 8 hand-curated cases committed to `data/eval/canary/cases.jsonl` (D-13 + D-14 Option D)

**Commit:** `6c01c12`

Replaced Plan 05-01's single-record placeholder with 8 hand-curated cases against the Phase 3 corpus (AAPL/MSFT/NVDA/V/PG — all from the 9 fully-covered tickers per Phase 3 STATE.md; AMZN/META/XOM/GOOGL/LLY/WMT avoided per the partial-Item-regex coverage note). Each case carries the seven schema fields including the new `mode` field (Option D resolution).

**Failure-mode coverage** (RESEARCH §7 four cross-encoder failure modes):

| Mode | Case IDs | Count |
|------|---------|-------|
| Lexical-but-misleading (A) | C-01, C-05, C-06 | 3 |
| Near-duplicate boilerplate (B) | C-03, C-07 | 2 |
| Multi-aspect (C) | C-02, C-04, C-08 | 3 |
| Negation (D) | — | 0 (deferred — Plan 05-07 may add 1-2 negation cases to round out the taxonomy under real-mode verification) |

**Per-case rationale + gold:**

| # | case_id | Ticker | Year | Item | Gold chunk_id(s) | Failure mode |
|---|---------|--------|------|------|------------------|--------------|
| 1 | C-01-aapl-supply-chain-outsourcing | AAPL | 2024 | Item 1A | AAPL-FY2024-Item-1A-007 | Lexical-but-misleading — supplier concentration / China-India-Japan-Taiwan-Vietnam outsourcing vs generic supply-chain boilerplate |
| 2 | C-02-msft-openai-partnership | MSFT | 2024 | Item 1 | MSFT-FY2024-Item-1-004 | Multi-aspect — partnership + Azure-as-exclusive-cloud-provider; adjacent Item 1 AI/Copilot/Azure chunks lack both anchors |
| 3 | C-03-nvda-china-export-controls | NVDA | 2024 | Item 1A | NVDA-FY2024-Item-1A-018, NVDA-FY2024-Item-1A-037 | Near-duplicate boilerplate — USG GPU/AI semiconductor export controls + Jan-2025 AI Diffusion IFR Tier-2 designation |
| 4 | C-04-nvda-data-center-vs-gaming | NVDA | 2024 | Item 7 | NVDA-FY2024-Item-7-006 | Multi-aspect — Data Center / Gaming / Professional Visualization / Automotive enumeration + Data Center 142% YoY |
| 5 | C-05-v-cross-border-volume | V | 2024 | Item 7 | V-FY2024-Item-7-001 | Lexical-but-misleading — 10% net-revenue increase attribution to cross-border-volume growth + client incentives offset |
| 6 | C-06-aapl-services-revenue-growth | AAPL | 2024 | Item 7 | AAPL-FY2024-Item-7-003 | Lexical-but-misleading — Services gross margin in MD&A (not Apple Music / App Store / iCloud pricing chunks) |
| 7 | C-07-pg-foreign-currency-risk | PG | 2024 | Item 1A | PG-FY2024-Item-1A-001 | Near-duplicate boilerplate — quantitative anchor >50% non-US net sales + foreign-currency debt + derivatives |
| 8 | C-08-nvda-geopolitical-taiwan-china | NVDA | 2024 | Item 1A | NVDA-FY2024-Item-1A-008 | Multi-aspect — Taiwan/China geopolitics AND suppliers/contract-manufacturers/assembly-partners concentration |

**Verification:** every gold_chunk_id was confirmed to exist in `data/corpus/chunks/<TICKER>/FY2024.jsonl` before commit (verifier script in `/tmp/claude/verify_gold.py`, since deleted; the schema-validation runs on every PR via `test_reranker_canary_stub_mode`).

**CONTEXT.md amendment** (`.planning/phases/05-retrieval-hybrid-rerank/05-CONTEXT.md`, gitignored): the D-14/D-15 amendment block documents the Option D resolution. The CONTEXT.md file itself was created by this task because the file did not exist at the worktree base — only the decision IDs were referenced elsewhere. The amendment captures: (a) the empirical finding (stub reranker structurally cannot beat stub dense-only); (b) the resolution (mode field, schema-only stub gate, workflow_dispatch real-mode bite-point); (c) the deferred ticket (stub-reranker discriminative-power redesign).

---

### Task 2 — Canary test driver implemented per RESEARCH §9 Pattern A (4 test functions)

**Commit:** `9742ce5`

Full rewrite of `tests/test_reranker_canary.py` with the four test functions per Option D semantics:

| Test function | Marker | Status | Body |
|---------------|--------|--------|------|
| `test_cases_loaded` | — | Passes | D-13 schema gate — `_load_cases()` returns ≥5 records; every record has the seven required fields (case_id, question, gold_chunk_ids, ticker, fiscal_year, rationale, mode). |
| `test_reranker_canary_stub_mode` | — | Passes (schema-only under Option D) | Asserts the seven schema fields per record, `mode in {real, stub, None}`, `gold_chunk_ids` is a non-empty `list[str]`. Does NOT run the rerank-vs-dense-only differential. |
| `test_failure_message_quotes_claude_md` | — | Passes | Pitfall 6 doubled-defense — three substrings asserted in BOTH _CLAUDE_MD_QUOTE (test-local) AND _CLAUDE_MD_HARD_GATE (retriever module). |
| `test_reranker_canary_real_mode` | `@pytest.mark.real` (outer) + `@pytest.mark.xfail(strict=True, reason="Plan 05-07 — real-mode verification under workflow_dispatch")` (inner) | Deselected by default `-m "not real"`; collectable via `-m real` | Strict D-14 differential — `rerank_top3_hits > dense_only_top3_hits AND rerank_top3_hits >= 5` using `make_retriever(cfg=real)` vs `Retriever(bundle.model_copy(update={"reranker": NullReranker()}), stores, cfg)`. |

**Module-top _CLAUDE_MD_HARD_GATE import promotion** (per the Plan 05-06 Task 2 directive): Plan 05-01 Task 2 placed `from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE` INSIDE the test body as the Wave-0 xfail hook (ImportError → genuine xfail before Plan 05-05 shipped retriever.py). Plan 05-06 Task 2 promoted this import to the module-top imports block. The standard wave-flip pattern.

**Source assertions met:**
- `head` of file contains `from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE` at module top (line 97, right after the long docstring).
- No in-function `from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE` remains.
- Four required test functions exist exactly once each (`grep -cE '^def test_(cases_loaded|reranker_canary_stub_mode|failure_message_quotes_claude_md|reranker_canary_real_mode)'` returns 4).
- `@pytest.mark.real` decorator present above `def test_reranker_canary_real_mode`.
- Zero `@pytest.mark.xfail` decorators on the three non-real tests.

**Test outcomes:**
- `uv run pytest tests/test_reranker_canary.py -m "not real" -ra -q` → **3 passed, 1 deselected** in 0.08s
- `uv run pytest tests/test_reranker_canary.py -m real --collect-only -q` → **test_reranker_canary_real_mode collected** (3 deselected)
- `uv run pytest -ra -q -m "not real"` → **121 passed, 2 skipped, 4 deselected, 0 xfailed** (up from Plan 05-05's 119 passed + 2 xfailed baseline — net +2 passing tests, -2 xfails)
- `uv run mypy --strict packages/*/src` → **47 source files, 0 errors**
- `bash scripts/check_index_wraps.sh && bash scripts/check_adapter_wraps.sh && bash scripts/check_ingest_wraps.sh` → **all three exit 0**

---

### Task 3 — Named CI step `Reranker canary (stub-mode acceptance gate) (RET-03)` added to default lint-and-test job

**Commit:** `b2567a3`

Added one named step to `.github/workflows/ci.yml` in the default `lint-and-test` job, positioned right after the existing `uv run pytest -ra -q` step. The step's comment block references CLAUDE.md and the verbatim BGE-512-token-truncation note so anyone reading the CI yaml sees the Pitfall 6 hard-gate paragraph at the gate's call site.

**Verbatim yaml block landed:**

```yaml
      - name: Reranker canary (stub-mode acceptance gate) (RET-03)
        # Phase 5 STRUCTURAL ACCEPTANCE GATE. Per CLAUDE.md: if this fails,
        # look at BGE 512-token truncation FIRST before suspecting hybrid
        # retrieval, RRF, or chunk size.
        run: uv run pytest tests/test_reranker_canary.py -ra -q -m "not real"
```

**NO changes** to the `real-index-build` job at lines 240-290 — its existing `uv run pytest -m real -ra -q` step at line 286 auto-collects `test_reranker_canary_real_mode` because of the `@pytest.mark.real` decoration (RESEARCH §10 explicit recommendation: "the existing wiring picks it up").

**Source assertions met:**
- `grep -c "Reranker canary (stub-mode acceptance gate)" .github/workflows/ci.yml` returns 1.
- The step's `run:` is `uv run pytest tests/test_reranker_canary.py -ra -q -m "not real"`.
- YAML parses cleanly (`yaml.safe_load` succeeds; canary step is a member of `jobs.lint-and-test.steps`).
- No duplicate canary step in `jobs.real-index-build.steps`.
- The comment block contains both `CLAUDE.md` and `BGE 512-token truncation FIRST`.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] CONTEXT.md did not exist at the worktree base**

- **Found during:** Task 1 setup (reading the planning context).
- **Issue:** the Plan 05-06 frontmatter referenced `@.planning/phases/05-retrieval-hybrid-rerank/05-CONTEXT.md` and the objective required adding an amendment block "immediately after the existing D-15" — but `05-CONTEXT.md` did not exist (was never created during Phase 5 planning; D-13/D-14/D-15/D-16/D-17 were referenced from Plan 05-06 PLAN.md `<interfaces>` and from 05-01-SUMMARY.md and from PATTERNS/RESEARCH but had no canonical anchor file).
- **Fix:** created the file with a minimal canonical D-13..D-17 register (extracted verbatim from Plan 05-06 PLAN.md `<interfaces>` and PLAN 05-06 task descriptions) followed by the Plan 05-06 Option D amendment block.
- **Files modified:** `.planning/phases/05-retrieval-hybrid-rerank/05-CONTEXT.md` (created; gitignored per the project's `.planning/` rule; not in any commit but force-committable later if needed).
- **Commit:** part of `6c01c12` Task 1 work (the CONTEXT.md change is local-only because `.planning/` is gitignored; this SUMMARY.md force-committed via `git add -f` carries the public-repo record).

**2. [Rule 4 — Scope-boundary deferral] Pre-existing ruff + black warnings in Plan 05-05's `factory.py` + `retriever.py`**

- **Found during:** Task 2 verification pass (`uv run ruff check packages/` + `uv run black --check packages/`).
- **Issue:** 8 ruff errors + 2 black reformat warnings, all in files modified by Plan 05-05 (`packages/docintel-core/src/docintel_core/adapters/factory.py` and `packages/docintel-retrieve/src/docintel_retrieve/retriever.py`). The errors include `I001` (import sorting under `if TYPE_CHECKING:`), `UP037` (string forward reference `-> "Retriever"` can be unquoted), `RUF100` (unused `# noqa: F821` / `# noqa: BLE001` directives), and `RUF022` (`__all__` not sorted).
- **Why deferred (NOT auto-fixed):** SCOPE BOUNDARY rule — these are pre-existing in the worktree base (`1ec2165`) from Plan 05-05's commits (`75c4b36 feat(05-05): GREEN — make_retriever(cfg) factory…` and `ac964ad feat(05-05): GREEN — Retriever class…`). Plan 05-06 did not introduce them. They were never CI-checked because no `phase/5-*` PR has been pushed to GitHub yet (the `main` branch's most recent CI run was for Phase 4); the Plan 05-05 plan-level pytest pass + mypy clean preceded the ruff regression.
- **Action:** logged to `.planning/phases/05-retrieval-hybrid-rerank/deferred-items.md` with full per-file breakdown and a recommended closure path (a small Plan-05-05 follow-up or a Plan 05-08 polishing plan running `uv run ruff check --fix packages/ && uv run black packages/`). The fix is non-trivial for the UP037 case because Plan 05-05 INTENTIONALLY used the string forward reference per Pattern S5 (lazy-import discipline); the closure path needs a Plan-05-05 follow-up, not a Plan-05-06 hotfix.

No other deviations from the plan as amended by the user's Option D resolution.

---

## Threat Flags

None new beyond Plan 05-06's documented threat model. The plan's STRIDE threat register (T-5-V5-03-canary, T-5-V5-03-cleanup-PR, T-5-V5-04-corpus-drift, T-5-V5-curation-rot) all remain mitigated:

- **T-5-V5-03-canary** (BGE tokenizer drift) — mitigation `_CLAUDE_MD_QUOTE` + `_CLAUDE_MD_HARD_GATE` doubled-defense intact; `test_failure_message_quotes_claude_md` asserts both constants on every PR.
- **T-5-V5-03-cleanup-PR** (paraphrasing the verbatim quote) — same mitigation as above; any paraphrase in either constant fires red CI.
- **T-5-V5-04-corpus-drift** (cases.jsonl gold_chunk_ids drift if Phase 3 re-chunks) — the chunk_map cardinality check in `Retriever.__init__` (Plan 05-05 D-10 + Pitfall 7) raises `ValueError` before the canary test even starts; cardinality mismatch surfaces with the rebuild-command pointer.
- **T-5-V5-curation-rot** (rationale documentation rot) — accepted risk per Plan 05-06; Phase 11 ablation reports will surface stale rationales.

---

## Known Stubs

None new. The Phase 5 D-08 ablation seam (`NullReranker`) is an intentional contract; the canary's real-mode test consumes it to build the dense-only baseline.

---

## Deferred Issues

**1. Stub-reranker discriminative-power redesign** — target Phase 11 (ablation) or v2 / Phase 14. See `.planning/phases/05-retrieval-hybrid-rerank/deferred-items.md` for the architectural detail. Acceptance bar: the redesigned `StubReranker.rerank` must produce `rerank_top3_hits > dense_only_top3_hits AND rerank_top3_hits >= 5` against the existing `data/eval/canary/cases.jsonl` IN STUB MODE. Once met, `test_reranker_canary_stub_mode` can be promoted from schema-only back to the strict D-14 differential.

**2. Plan 05-05 ruff + black warnings** — target Plan 05-05 follow-up cleanup PR (or a Plan 05-08 polishing plan). 8 ruff errors + 2 black reformat warnings in `factory.py` + `retriever.py` + `__init__.py`. None affect Phase 5's structural acceptance gate; all are stylistic. See `.planning/phases/05-retrieval-hybrid-rerank/deferred-items.md` for the per-file breakdown.

**3. Negation-failure-mode case curation** — the four-mode RESEARCH §7 taxonomy has 3 lexical-but-misleading + 2 near-duplicate-boilerplate + 3 multi-aspect cases; zero negation cases. Plan 05-07 may add 1-2 negation-failure-mode cases (e.g. "What is NVIDIA NOT exposed to in Taiwan?" with a gold chunk that defines the negation cleanly) under real-mode verification. Optional — the four modes are not equally common in 10-K text, and the existing 8-case mix already exercises the rerank-vs-dense-only differential across the bulk of the failure space.

---

## Self-Check: PASSED

**Artifact verification (file existence + commits):**

- `data/eval/canary/cases.jsonl` exists with 8 records, all 7 required fields per record, all gold_chunk_ids resolve to corpus chunks. **FOUND.**
- `tests/test_reranker_canary.py` has 4 test functions (test_cases_loaded, test_reranker_canary_stub_mode, test_failure_message_quotes_claude_md, test_reranker_canary_real_mode). **FOUND.**
- `.github/workflows/ci.yml` contains exactly one step named `Reranker canary (stub-mode acceptance gate) (RET-03)`. **FOUND.**
- Commits: `6c01c12` (Task 1), `9742ce5` (Task 2), `b2567a3` (Task 3). **FOUND.**

**Behavior verification:**

- `uv run pytest tests/test_reranker_canary.py -m "not real" -ra -q` → 3 passed, 1 deselected. **GREEN.**
- `uv run pytest tests/test_reranker_canary.py -m real --collect-only -q` → `test_reranker_canary_real_mode` collected. **GREEN.**
- `uv run pytest -ra -q -m "not real"` → 121 passed, 2 skipped, 4 deselected, 0 xfailed. **GREEN.**
- `uv run mypy --strict packages/*/src` → 47 source files, 0 errors. **GREEN.**
- `bash scripts/check_index_wraps.sh && bash scripts/check_adapter_wraps.sh && bash scripts/check_ingest_wraps.sh` → all three exit 0. **GREEN.**

---

## What's next

**Plan 05-07** runs the real-mode canary test under `workflow_dispatch` against the real bge-small-en-v1.5 embedder + bge-reranker-base reranker + qdrant dense store + bm25s sparse store, records the empirical `rerank_top3_hits` vs `dense_only_top3_hits` numbers in the eval reports, and removes the `@pytest.mark.xfail(strict=True, reason="Plan 05-07 — real-mode verification under workflow_dispatch")` marker from `test_reranker_canary_real_mode` once the strict D-14 criterion is verified. After Plan 05-07 lands, Phase 5 is closed.

The deferred stub-reranker discriminative-power redesign (target Phase 11 or v2 / Phase 14) does NOT block Phase 5 closure — the Phase 5 STRUCTURAL ACCEPTANCE GATE (RET-03) is empirically verified by Plan 05-07 in real-mode under workflow_dispatch; the structural framing in ROADMAP.md stands.
