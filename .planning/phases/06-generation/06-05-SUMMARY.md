---
phase: 06-generation
plan: 05
subsystem: generation
tags: [stub-adapter, refusal-sentinel, chunk-regex, pitfall-5, pitfall-9, single-source-of-truth, d-11, d-12, gen-04]

requires:
  - phase: 06-generation/plan/02
    provides: REFUSAL_TEXT_SENTINEL in docintel_core.types (the canonical sentinel home)
  - phase: 06-generation/plan/03
    provides: _CHUNK_RE in docintel_generate.parse (the canonical regex home)
  - phase: 06-generation/plan/04
    provides: Generator + GenerationResult + make_generator (consumers of the unified sentinel + regex)
provides:
  - packages/docintel-core/src/docintel_core/adapters/stub/llm.py — _STUB_REFUSAL re-aliases REFUSAL_TEXT_SENTINEL from docintel_core.types; _CHUNK_RE re-imports from docintel_generate.parse; import re removed; stub seam behavior unchanged
  - Pitfall 5 mitigation closed (no value drift between Phase 2 placeholder and Phase 6 canonical refusal text)
  - Pitfall 9 cycle resolved end-to-end (REFUSAL_TEXT_SENTINEL home in core; _CHUNK_RE home in generate.parse; one stub-side cross-package import allowed per CONTEXT.md D-12 line 107)
  - GEN-04 acceptance: stub-mode refusal path emits the SAME byte-string as real-mode hard-refusal path (Generator Step B)
affects: [06-06 judge adapter migration (orthogonal — Plan 06-06 owns adapters/real/judge.py and structured-output dispatch), 06-07 EVAL-02 manifest reader + xfail-removal sweep, 09-metrics MET-03 faithfulness eval (now sees unified sentinel across stub + real)]

tech-stack:
  added: []
  patterns:
    - Pitfall-9 cycle-safe single-source-of-truth — _STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL imported from docintel_core.types (never reverse)
    - Pitfall-5 value-drift defense — backward-compat alias (the _STUB_REFUSAL NAME is retained for existing test imports; the VALUE tracks the canonical constant in docintel_core.types)
    - Cross-package single-source regex — from docintel_generate.parse import _CHUNK_RE inside adapters/stub/llm.py. The CONTEXT.md D-12 explicit allowance for ONE stub-side cross-package import. Cycle is one-way at runtime (make_adapters returns stub only when llm_provider="stub", at which point docintel-generate is already loaded by the test harness)
    - Module-scope-name-resolution-via-import-alias — the in-class `_CHUNK_RE.findall(prompt)` reference at line 77 needs no edit; Python binds the module-scope `_CHUNK_RE` to the imported Pattern instance transparently

key-files:
  created:
    - .planning/phases/06-generation/06-05-SUMMARY.md
  modified:
    - packages/docintel-core/src/docintel_core/adapters/stub/llm.py (the single production change — sentinel + regex retirement)
    - tests/test_adapters.py (Rule 1 amendment — retire byte-literal substring assertion in favor of symbolic _STUB_REFUSAL identity check)
    - tests/test_generator_search_integration.py (xfail-reason re-tag — hero test remains xfail-strict; root-cause now documented as stub-template repr-list issue, not as Wave-2 make_generator absence)

key-decisions:
  - "Plan acceptance scope is the sentinel + regex retirement ONLY. Plan 06-05's `<acceptance_criteria>` and `<success_criteria>` make NO claim that test_hero_comparative_stub flips from xfail to pass. The orchestrator's spawn prompt overshot — claiming the hero test would XPASS — but the plan as written does not promise it. The fail mode is structural and orthogonal to D-11/D-12: the stub LLM's `[STUB ANSWER citing chunk_ids]` template emits a Python repr-list of full D-14 header strings (e.g. 'chunk_id: TSLA-FY2023-Item-8-063 | company: TSLA | fiscal_year: 2023 | section: Item 8'), and Generator Step D's _CHUNK_RE.findall(completion.text) extracts those entire header strings as candidate citation IDs — none of which match {c.chunk_id for c in retrieved}, so all are dropped as hallucinations and cited_chunk_ids comes back empty. Re-tagging the xfail-reason with the correct root cause is the honest delivery; reworking the stub template is a future-plan responsibility."
  - "tests/test_adapters.py::test_stub_llm_refusal was byte-literal substring-asserting against the Phase 2 placeholder ('\"REFUSAL\" in upper or \"No evidence\" in text'). Plan 06-05's D-11 retirement of that value makes the substring assertion fail. Rule 1 (auto-fix bug introduced by the planned value change): swap to symbolic identity assertion (response.text == _STUB_REFUSAL == REFUSAL_TEXT_SENTINEL). This is the canonical pattern — tests assert against the named symbol, not the byte-literal. CONTEXT.md line 120 in the plan explicitly anticipated this and instructed amending such assertions."
  - "import re removed from adapters/stub/llm.py. Verified by grep ('^import re$' returns 0 matches) and by mypy --strict (no unused-import or other errors)."
  - "Module docstring updated to retire the 'Phase 6 may replace this constant' line, replaced with 'imported from the canonical Phase 6 homes' language. The deviation note inside the _STUB_REFUSAL docstring was tightened to avoid containing the literal bracketed-string '[STUB REFUSAL] No evidence found in retrieved context.' so that the source-level acceptance grep `! grep -q '\\[STUB REFUSAL\\] No evidence found' adapters/stub/llm.py` passes cleanly. Documentation-time mention of the retired value would have been semantically harmless but failed the grep gate as written."
  - "Pre/post line count: 96 → 112 (+16 lines). Plan's `<output>` informational note expected ~10 lines shorter; the actual file grew because the new docstrings explaining D-11/D-12 contract (back-compat alias, single-source rationale, Pitfall 9 cycle resolution) are longer than the retired in-file _CHUNK_RE block. This is intentional: docstring contracts are load-bearing for Phase 9/10/13 readers."

patterns-established:
  - "Phase 6 cross-package alias pattern: in-file `_NAME: Final[type] = imported_canonical_name` re-export preserves the existing public name for back-compat while making the canonical source visible at the import. Mypy --strict treats this as a normal Final assignment."
  - "Phase 6 cross-package regex re-import pattern: bare `from <other_package> import _NAME` for compiled-regex constants. No alias needed; the module-scope name binds to the same Pattern instance. The in-class `_NAME.findall(...)` call resolves to the imported instance transparently — no class-body source edit required."
  - "Allowed-cross-package-import is justified inline with a comment block citing the CONTEXT.md decision (D-12 line 107). The single allowed direction is annotated, the inverse cycle is explicitly called out as resolved by the sentinel home in core."

---

# Phase 6 Plan 05: Stub LLM Adapter Sentinel + Regex Retirement Summary

Retired the Phase 2 placeholder `_STUB_REFUSAL` byte-literal value
(`"[STUB REFUSAL] No evidence found in retrieved context."`) in favor of the
canonical Phase 6 sentinel `REFUSAL_TEXT_SENTINEL` imported from
`docintel_core.types` (D-11); retired the in-file `_CHUNK_RE` regex definition
in favor of re-importing the canonical instance from `docintel_generate.parse`
(D-12). Single source of truth across stub + real + Phase 7 Citation parser is
now structurally enforced.

## What landed

Single production file edit: `packages/docintel-core/src/docintel_core/adapters/stub/llm.py`.

**Edit 1 — module docstring updated** (lines 1-15). The phrase
"forward compatibility with Phase 6 prompt schema formalisation" was
replaced with "imported from the canonical Phase 6 homes
(`docintel_generate.parse._CHUNK_RE` and
`docintel_core.types.REFUSAL_TEXT_SENTINEL` respectively); this module
re-aliases them as `_CHUNK_RE` and `_STUB_REFUSAL` for backward-compat with
existing tests + Phase 2 D-16 contract."

**Edit 2 — imports reorganized** (lines 17-29). The `import re` line was
removed (no longer needed). Two new lines added: `from docintel_core.types
import REFUSAL_TEXT_SENTINEL` (in-package upward dep — fine) and
`from docintel_generate.parse import _CHUNK_RE` (the one allowed cross-package
import per CONTEXT.md D-12 line 107, justified inline with a four-line comment
explaining the cycle direction).

**Edit 3 — constants block** (lines 31-46). `_STUB_REFUSAL: Final[str] =
REFUSAL_TEXT_SENTINEL` replaces the old byte-literal assignment; the new
docstring documents the D-11 + D-12 promotion + the back-compat-alias
rationale (the `_STUB_REFUSAL` NAME is retained for existing test imports;
new code should import `REFUSAL_TEXT_SENTINEL` from `docintel_core.types`
directly). The `_CHUNK_RE` definition block is gone — replaced by a four-line
comment explaining the move and pointing readers at the import line above.

**Edit 4 — `StubLLMClient.complete()` body** (lines 71+). UNCHANGED — the
template branch still emits `[STUB ANSWER citing {chunk_ids}]` verbatim per
D-12 "no change needed", and the refusal branch's `text = _STUB_REFUSAL`
assignment now resolves to the new canonical 63-char byte-string transparently.

## Verification (all PASS)

```text
# Byte-identity
uv run python -c "
  from docintel_core.adapters.stub.llm import _STUB_REFUSAL, _CHUNK_RE
  from docintel_core.types import REFUSAL_TEXT_SENTINEL
  from docintel_generate.parse import _CHUNK_RE as canonical
  assert _STUB_REFUSAL == REFUSAL_TEXT_SENTINEL == 'I cannot answer this question from the retrieved 10-K excerpts.'
  assert _CHUNK_RE is canonical
" → OK

# Behavior
uv run python -c "
  from docintel_core.adapters.stub.llm import StubLLMClient, _STUB_REFUSAL
  c = StubLLMClient()
  r1 = c.complete('hello world')
  assert r1.text == _STUB_REFUSAL  # refusal-path
  r2 = c.complete('Apple revenue [AAPL-FY2024-Item-1A-007] grew.')
  assert '[STUB ANSWER citing' in r2.text and 'AAPL-FY2024-Item-1A-007' in r2.text  # template-path
" → OK

# Source-level acceptance grep
grep -c "^_STUB_REFUSAL: Final\[str\] = REFUSAL_TEXT_SENTINEL"              → 1  (alias in place)
grep -c "REFUSAL_TEXT_SENTINEL"                                              → 5  (import + alias + 3 docstring refs)
grep -c "from docintel_generate.parse import _CHUNK_RE"                      → 1  (cross-package import per D-12)
grep -c "\[STUB REFUSAL\] No evidence found"                                 → 0  (old literal fully retired)
grep -c "^_CHUNK_RE: Final\[re\.Pattern\[str\]\]"                            → 0  (in-file regex retired)
grep -E "^import re$" packages/.../stub/llm.py                               → no match (import re removed)

# CI grep gates (all four)
bash scripts/check_prompt_locality.sh   → exit 0
bash scripts/check_adapter_wraps.sh     → exit 0
bash scripts/check_index_wraps.sh       → exit 0
bash scripts/check_ingest_wraps.sh      → exit 0

# Type check
uv run mypy --strict packages/docintel-core/src/docintel_core/adapters/stub/llm.py → 0 errors
uv run mypy --strict packages/docintel-core/                                      → 0 errors across 23 files

# Test sweep
uv run pytest -ra -q -m "not real"
  → 138 passed, 2 skipped, 6 deselected, 2 xfailed in 34.49s
    (2 xfailed: test_hero_comparative_stub — stub-template repr-list issue, retagged
                test_deserialization_failure_returns_sentinel — Plan 06-06 sibling, untouched)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug introduced by planned value change] tests/test_adapters.py::test_stub_llm_refusal**

- **Found during:** Task A verify step (pytest tests/test_adapters.py).
- **Issue:** The pre-edit assertion `"REFUSAL" in response.text.upper() or "No evidence" in response.text` was byte-literal-substring-asserting against the Phase 2 placeholder value. Plan 06-05's D-11 retirement of that value broke the assertion (the new canonical sentinel contains neither "REFUSAL" nor "No evidence"). The plan's `<interfaces>` block (CONTEXT.md line 120) anticipated this and explicitly instructed amending any such byte-literal assertions to symbolic references.
- **Fix:** Replace with symbolic byte-identity assertions against `_STUB_REFUSAL` and `REFUSAL_TEXT_SENTINEL`. This is the canonical pattern across the codebase (tests assert against named symbols, not against literal byte values).
- **Files modified:** `tests/test_adapters.py` (lines 112-131; +8 lines of docstring + symbolic-assertion body).
- **Commit:** `ad83123`.

**2. [Rule 1 - Bug from removed-unused-import] tests/test_generator_search_integration.py orphan `import pytest`**

- **Found during:** xfail-marker removal evaluation. The original `import pytest` was used only to provide `pytest.mark.xfail(...)`; removing the marker would orphan the import (Ruff F401).
- **Status:** N/A — see deviation 3 below. The xfail marker was reinstated with a corrected reason, so `import pytest` is still in use. No final removal needed.

### Acceptance-Critical Re-evaluation

**3. [Rule 4 → Auto-corrected after re-reading plan acceptance] hero test remains xfail-strict — re-tagged with correct root-cause**

- **Spawn-prompt claim:** The orchestrator's prompt stated "remove the xfail marker on `test_hero_comparative_stub` so the test XPASSes cleanly (it will now PASS because the stub LLM emits the canonical sentinel + the chunk_id pattern matches `_CHUNK_RE`)."
- **Actual behavior:** With xfail removed, the test FAILS (not XPASSes). The fail mode is unrelated to the sentinel + regex changes in this plan. The stub LLM's `[STUB ANSWER citing chunk_ids]` template emits `chunk_ids` as a Python `repr`-list of the full D-14 header strings (e.g. `'chunk_id: TSLA-FY2023-Item-8-063 | company: TSLA | fiscal_year: 2023 | section: Item 8'`). The Generator's Step D `_CHUNK_RE.findall(completion.text)` then matches the OUTERMOST brackets, extracting each full header string as a candidate chunk-id — none of which match `{c.chunk_id for c in retrieved}`, so all are dropped as hallucinated IDs. `cited_chunk_ids` comes back empty and `assert len(r.cited_chunk_ids) >= 1` fails.
- **Verification that this is independent of Plan 06-05:** I stashed my edits, removed the xfail marker on the pre-edit `phase/6-generation` tip (9b1a651), and re-ran the hero test — it failed with the IDENTICAL failure mode (cited_chunk_ids=[]). The root cause pre-existed Plan 06-05.
- **Plan acceptance reality:** Plan 06-05's `<acceptance_criteria>` (lines 236-251) and `<success_criteria>` (lines 267-275) make NO claim that the hero test flips from xfail to pass. The acceptance criteria are scoped to the sentinel + regex retirement and to existing Phase 2 stub tests passing. The orchestrator-prompt claim was overshot.
- **Action taken:** Keep the xfail-strict marker on `test_hero_comparative_stub` but re-tag its reason from "Wave 2 — Plan 06-04 ships make_generator(cfg) integration" (now misleading — Plan 06-04 already shipped `make_generator`) to a precise statement of the actual blocker: the stub's template emits a Python repr-list of full D-14 header strings rather than bare `[chunk_id]` brackets, and the stub-template rework is out of scope for Plan 06-05. Plan 06-07 (xfail-removal sweep) or a follow-up plan can address it.
- **Files modified:** `tests/test_generator_search_integration.py` (re-tagged xfail reason).
- **Commit:** `ad83123`.
- **Rationale for not auto-fixing the stub template (Rule 4 — architectural):** Rewriting the stub's `[STUB ANSWER citing ...]` template to emit bare `[chunk_id]` brackets is a Phase 2 D-16 amendment, not a Phase 6 D-12 amendment. It crosses adapter-protocol boundaries, requires re-validating the existing Phase 2 ADP-04 determinism tests, and would meaningfully change behavior at the seam. Plan 06-05 explicitly says (lines 220-222): "The `StubLLMClient.complete` method's body should NOT be modified by this plan." Doing so unilaterally would violate Rule 4 — surface as deferred work instead.

## Deferred Work

**Stub-template rework so `test_hero_comparative_stub` flips xfail → pass.** The
existing template at `packages/docintel-core/src/docintel_core/adapters/stub/llm.py`
lines 73-79 emits `f"Based on the provided context: {prompt[:200]}... [STUB
ANSWER citing {chunk_ids}]"` where `chunk_ids` is a Python list of full D-14
header strings. The Generator's Step D regex parse extracts those entire header
strings (matched by the outermost `[` `]` brackets) and rejects them as
hallucinated IDs against `{c.chunk_id for c in retrieved}`. Two fix paths:

1. **Template-rewrite path.** Change the stub's template to emit bare
   `[chunk_id]` brackets per the D-14 schema, e.g.
   `f"Based on the provided context: ... [{chunk_ids[0]}] [{chunk_ids[1]}] ..."`.
   But `chunk_ids` as extracted by `_CHUNK_RE.findall(prompt)` from the D-14
   prompt is the LIST OF HEADER STRINGS (each match is the full
   `chunk_id: X | company: Y | ...`), so the template would need to parse out
   the bare ID from each header before emitting it.
2. **Regex-narrowing path.** Tighten `_CHUNK_RE` to match only bare chunk_ids
   (e.g. `r"\[([A-Z]{1,5}-FY\d{4}-Item-[\w]+-\d{3})\]"`) so the D-14 header
   matches are skipped and only true `[chunk_id]` citations are extracted in
   Step D. This is the cleaner option — it aligns with the citation-bracket
   semantic the Phase 7 Citation parser will also consume.

Either path is a P6 follow-up or a P7 prerequisite. Plan 06-07's xfail-removal
sweep can pick it up; alternatively the verifier on Phase 6 close can document
this as P6-deferred.

## Authentication Gates

None — Plan 06-05 is fully stub-mode + offline.

## Self-Check: PASSED

Confirmed via:

- `git log --oneline -3` shows commits `cd0e393` (production edit) and
  `ad83123` (test amendments) on top of Wave-2 tip `9b1a651`.
- `[ -f packages/docintel-core/src/docintel_core/adapters/stub/llm.py ]` → 1 (file present, 112 lines).
- `git grep "\[STUB REFUSAL\]" packages/` → exit 1 (no matches — old sentinel fully retired from the codebase).
- `git grep "_STUB_REFUSAL" packages/` → 6 matches all in `adapters/stub/llm.py` (docstring + alias).
- Behavior assertion: `_STUB_REFUSAL is REFUSAL_TEXT_SENTINEL` → True (Python interns short strings, so this is identity-equal as well as value-equal).
- Behavior assertion: `_CHUNK_RE is docintel_generate.parse._CHUNK_RE` → True (the import binds the SAME `re.Pattern` instance — identity check stronger than value-equality).
- Pre/post line count: 96 → 112 (+16 lines; informational only — the plan's "expect ~10 lines shorter" was a forecast, not an acceptance criterion).

## Metrics

- Plan duration: ~30 minutes wall-clock
- Tasks completed: 1/1 (Plan 06-05 has one task: "Task A — Update _STUB_REFUSAL value via REFUSAL_TEXT_SENTINEL import + retire in-file _CHUNK_RE")
- Atomic commits: 2 (`cd0e393` production edit; `ad83123` test amendments)
- Files modified: 3
  - `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` (the single production change)
  - `tests/test_adapters.py` (Rule 1 amendment)
  - `tests/test_generator_search_integration.py` (xfail-reason re-tag)
- Test deltas: 138 passed (+0 from baseline; the predicted regression in `test_stub_llm_refusal` was Rule-1-fixed to a symbolic assertion). 2 xfailed (`test_hero_comparative_stub` re-tagged with corrected reason; `test_deserialization_failure_returns_sentinel` Plan 06-06's deliverable, untouched).
- mypy --strict: 23/23 files clean across `packages/docintel-core/`.
- CI grep gates: 4/4 exit 0.
- Completed: 2026-05-15T18:28:18Z
