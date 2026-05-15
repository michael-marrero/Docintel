---
phase: 06-generation
plan: 03
subsystem: generation
tags: [prompts, sha256-hash, final-str, pitfall-3, pitfall-9, pitfall-10, chunk-regex, refusal-sentinel, gen-01, gen-02]

requires:
  - phase: 06-generation/plan/01
    provides: tests/test_prompt_version_hash.py + tests/test_prompt_locality.py xfail scaffolds
  - phase: 06-generation/plan/02
    provides: docintel-generate package skeleton + REFUSAL_TEXT_SENTINEL in docintel_core.types + scripts/check_prompt_locality.sh
provides:
  - packages/docintel-generate/src/docintel_generate/prompts.py — canonical prompt home with three Final[str] prompts (SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT) + four sha256[:12] hashes (_SYNTHESIS_HASH, _REFUSAL_HASH, _JUDGE_HASH, PROMPT_VERSION_HASH) + _h() helper + build_judge_user_prompt() helper
  - packages/docintel-generate/src/docintel_generate/parse.py — canonical _CHUNK_RE compiled regex + is_refusal() boolean helper
  - packages/docintel-generate/src/docintel_generate/__init__.py — Wave-1 re-exports the four public prompt names alphabetically
  - GEN-01 (canonical prompt home) + GEN-02 (prompt-version hash) acceptance criteria fully landed
affects: [06-04 Generator + Step D citation parsing + refusal flag, 06-05 stub adapter _CHUNK_RE re-import, 06-06 judge migration consuming build_judge_user_prompt, 06-07 EVAL-02 manifest reader, 09-metrics MET-* readers, 10-eval-harness manifest header, 11-ablation per-prompt-hash localisation]

tech-stack:
  added: []
  patterns:
    - Final[str] module-level prompt constants with byte-exact sha256[:12] hashes computed at module import
    - Pitfall-9 cycle-safe single-source-of-truth — REFUSAL_PROMPT = REFUSAL_TEXT_SENTINEL imported from docintel_core.types (never reverse)
    - Pitfall-3 critical header comment guarding against whitespace/encoding drift in hashed prompt bodies
    - Per-prompt + combined hash layering (combined = _h(concatenation of per-prompt hashes)) for ablation-report drift localisation
    - Triple-quoted "\"\"\"\\" continuation form so the first newline is suppressed and the body starts at column 0
    - Anthropic-style XML-tag instruction convention (<context>...</context>) in SYNTHESIS_PROMPT
    - Module-level _CHUNK_RE: Final[re.Pattern[str]] (matches Phase 2 adapters/stub/llm.py:31 pattern verbatim)

key-files:
  created:
    - packages/docintel-generate/src/docintel_generate/prompts.py
    - packages/docintel-generate/src/docintel_generate/parse.py
    - .planning/phases/06-generation/06-03-SUMMARY.md
  modified:
    - packages/docintel-generate/src/docintel_generate/__init__.py (Wave-1 re-exports)
    - tests/test_prompt_version_hash.py (xfail-marker sweep — the three GEN-02 tests now pass)

key-decisions:
  - "Pitfall-3 fix vs RESEARCH §Example 1 body: the verbatim research example line-wrapped the refusal sentinel across two lines ('...emit\\nverbatim and ONLY this sentence: \"I cannot answer this question from the retrieved\\n10-K excerpts.\"'). That would have surfaced in LLM output as a literal newline mid-sentinel, breaking is_refusal() which uses byte-exact startswith() on the clean 63-char REFUSAL_TEXT_SENTINEL. Rule 1 deviation: reformatted that rule to keep the quoted sentence on one line ('...emit verbatim and ONLY this sentence (a single line, no line break): \"I cannot answer this question from the retrieved 10-K excerpts.\"'). SYNTHESIS_PROMPT now contains the byte-exact sentinel as a contiguous run."
  - "REFUSAL_PROMPT byte-equals REFUSAL_TEXT_SENTINEL per PLAN §must_haves.truths line 17 + Pitfall 9 single-source-of-truth. The RESEARCH example inlined the literal string (line 893-895); PLAN took precedence — REFUSAL_PROMPT: Final[str] = REFUSAL_TEXT_SENTINEL imported from docintel_core.types. The 63-char body is HASHED here for _REFUSAL_HASH but the string itself lives in core."
  - "Three xfail-strict markers removed from tests/test_prompt_version_hash.py (early sweep). Same precedent as commit 8681559 for Plan 06-02's prompt_locality sweep — keeps the suite green between waves rather than relying on Plan 06-07's Wave-4 sweep. Also dropped the now-orphaned 'import pytest' to stay ruff-clean. The same orphan still exists in tests/test_prompt_locality.py (introduced by 8681559) — left alone as out-of-scope per the scope-boundary rule."
  - "Public surface = the four module-level prompt constants only (D-01). Private constants (_h, _SYNTHESIS_HASH, _REFUSAL_HASH, _JUDGE_HASH, _CHUNK_RE) and helpers (build_judge_user_prompt, is_refusal) are intentionally NOT re-exported in __init__.py — consumers reach them via submodule import (from docintel_generate.prompts import _SYNTHESIS_HASH). Matches the leading-underscore convention."
  - "Duplicate _CHUNK_RE remains in adapters/stub/llm.py:31 (per PLAN §interfaces line 83 — Wave 1 only ADDS; Plan 06-05 retires the duplicate via re-import). Verification check 2 confirms the two definitions are pattern-byte-identical: both compile to r'\\\\[([^\\\\]]+)\\\\]'. The byte-identity is a hold-over invariant for Plan 06-06 to verify when Plan 06-05 lands."

patterns-established:
  - "Phase 6 prompt-home structural shape: from __future__ import annotations + import hashlib + from typing import Final + Pitfall-3 header comment + _h() helper + three Final[str] prompt constants + four Final[str] hash constants + module-level helper functions"
  - "Pitfall-9 sentinel-import direction lock: docintel_core.types owns canonical strings; docintel_generate.prompts and docintel_generate.parse import upward-stack; no reverse imports"
  - "Hash-byte-exactness Pitfall 3 documentation pattern: critical header comment block IMMEDIATELY ABOVE prompt definitions; module docstring also references the rule (defense-in-depth against future contributors who reflow whitespace 'for readability')"
  - "Sentinel-on-one-line invariant: when a prompt body must EMBED REFUSAL_TEXT_SENTINEL as a literal string the LLM is instructed to emit verbatim, the embedded substring MUST be a contiguous byte-run (no line wrap). is_refusal() asserts byte-exact startswith() on the embedded sentinel; a line-wrapped embedded sentinel would propagate the wrap to LLM output and break refusal detection."
  - "Optional early-xfail-sweep precedent extended (Plan 06-02 set the precedent for prompt_locality; Plan 06-03 extends to prompt_version_hash). Keeps suite green between waves; Plan 06-07's Wave-4 sweep now covers 14 of the original 20 instead of 17."

requirements-completed: [GEN-01, GEN-02]

duration: 7min
completed: 2026-05-15
---

# Phase 6 Plan 03: Wave 1 — Canonical Prompts + Chunk-ID Regex Summary

**The GEN-01 + GEN-02 fulcrum lands: three Final[str] prompts in `packages/docintel-generate/src/docintel_generate/prompts.py` with per-prompt + combined sha256[:12] hashes computed at module import; the canonical `_CHUNK_RE` compiled regex + `is_refusal()` helper land in `parse.py`; `__init__.py` re-exports the four public prompt names. Plan 06-07's Wave-4 sweep is partially front-loaded — three more xfail-strict markers removed from `tests/test_prompt_version_hash.py`.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-15T17:31:36Z
- **Completed:** 2026-05-15T17:38:06Z

## What Landed

### Three Final[str] prompts (D-07) — `packages/docintel-generate/src/docintel_generate/prompts.py`

```
SYNTHESIS_PROMPT len:  971 bytes  →  _SYNTHESIS_HASH = ec466290503d
REFUSAL_PROMPT   len:   63 bytes  →  _REFUSAL_HASH   = bf92b696078e
JUDGE_PROMPT     len:  723 bytes  →  _JUDGE_HASH     = 8e563d5fbce2
                                  →  PROMPT_VERSION_HASH = dab1bcf7379f
```

**`SYNTHESIS_PROMPT`** — answer-with-citations system prompt. Contains:
- XML-tag instruction ("<context>") per Anthropic prompt-engineering convention.
- Numbered rules block enforcing inline `[chunk_id]` bracket citations (D-10), no-invented-chunk-ids rule, the refusal-when-insufficient instruction with the byte-exact `REFUSAL_TEXT_SENTINEL` body (D-11), and comparative-question structuring guidance (Pitfall 10 mitigation — the hero question's failure mode).
- Locked fenced example with `[AAPL-FY2024-Item-1A-018]` and `[NVDA-FY2024-Item-7-042]` chunk_ids (D-10).
- Rule 1 deviation vs RESEARCH §Example 1: the embedded refusal sentinel is on a single line (no mid-sentinel line-wrap) to preserve byte-exact `is_refusal()` matching on LLM output.

**`REFUSAL_PROMPT`** — = `REFUSAL_TEXT_SENTINEL` imported from `docintel_core.types`. Pitfall 9 single-source-of-truth: the 63-char body string lives in core; this constant only re-uses it for hashing.

**`JUDGE_PROMPT`** — faithfulness-judge system prompt. Specifies the 4-field `JudgeVerdict` schema (`score` ∈ [0.0, 1.0], `passed = (score >= 0.5)`, `reasoning`, `unsupported_claims`) and the cross-family bias-mitigation rule. Plan 06-06 wires Anthropic `tools=[{strict:true}]` / OpenAI `response_format={'type': 'json_schema', 'strict': true}` against this schema.

### Four hash constants (D-08) — computed at module import via `_h()`

```python
_SYNTHESIS_HASH: Final[str] = _h(SYNTHESIS_PROMPT)
_REFUSAL_HASH:   Final[str] = _h(REFUSAL_PROMPT)
_JUDGE_HASH:     Final[str] = _h(JUDGE_PROMPT)
PROMPT_VERSION_HASH: Final[str] = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)
```

Per-prompt hashes give Plan 11 ablation reports + `generator_completed` structlog (Plan 06-04 telemetry) per-prompt drift localisation. The combined `PROMPT_VERSION_HASH` is Phase 10 EVAL-02 manifest's single bisection point.

### `build_judge_user_prompt(prediction, reference, rubric="")` helper (D-09 migration scaffold)

Plan 06-06 imports this helper inside `adapters/real/judge.py`, replacing the Phase 2 placeholder `_build_judge_prompt`. Format is locked: indexed reference passages (`[0]`, `[1]`, ...) followed by an optional rubric block.

### `_CHUNK_RE: Final[re.Pattern[str]]` + `is_refusal(text)` — `packages/docintel-generate/src/docintel_generate/parse.py`

`_CHUNK_RE` is byte-identical to `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:31` (`r"\[([^\]]+)\]"`). Plan 06-05 retires the stub-side definition via re-import. Between Wave 1 and Wave 3 the two definitions live in parallel; verification check 2 of this plan confirms byte-identity (`_CHUNK_RE.pattern == _STUB_CRE.pattern`).

`is_refusal(text)` returns `text.startswith(REFUSAL_TEXT_SENTINEL)` — single boolean check; no NLI, no embeddings. Plan 06-04 Generator Step D consumes it; Phase 7 Citation parser consumes it.

### `packages/docintel-generate/src/docintel_generate/__init__.py` Wave-1 re-exports

```python
__all__ = ["JUDGE_PROMPT", "PROMPT_VERSION_HASH", "REFUSAL_PROMPT", "SYNTHESIS_PROMPT"]
```

Alphabetical. Matches the Phase 5 `docintel-retrieve/__init__.py` convention. Private constants (`_h`, `_SYNTHESIS_HASH`, etc.) and helpers (`build_judge_user_prompt`, `is_refusal`) are not re-exported — consumers reach them via submodule import.

### `tests/test_prompt_version_hash.py` xfail-marker sweep

The three xfail-strict markers on `test_hash_format`, `test_per_prompt_hashes_exposed`, and `test_hash_sensitivity` are removed (all three assertion bodies pass cleanly now). Same precedent as commit 8681559 for Plan 06-02's prompt_locality sweep. Plan 06-07's Wave-4 sweep now covers 14 of the original 20 markers instead of 17. The now-orphaned `import pytest` is also removed so the test file is ruff-clean.

## Wave 1 Verification — All Six Checks Pass

1. **Combined hash determinism:** `_h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH) == PROMPT_VERSION_HASH` — ok.
2. **`parse._CHUNK_RE` pattern == `stub.llm._CHUNK_RE` pattern:** both = `r"\[([^\]]+)\]"` — ok. (Plan 06-05 retires the duplicate.)
3. **`bash scripts/check_prompt_locality.sh`:** exits 0 — `prompts.py` and `parse.py` are in the gate's allowlist; no new inline prompts leaked into adjacent files.
4. **`bash scripts/check_adapter_wraps.sh`:** exits 0 — Phase 2 wrap gate unchanged.
5. **`uv run pytest -ra -q -m "not real"`:** 127 passed, 2 skipped, 6 deselected, 13 xfailed. The 13 xfailed are Wave 2 / Wave 3 scaffolds (Generator, GenerationResult, judge structured output, make_generator) that Plan 06-04 and Plan 06-06 will satisfy. No NEW failures introduced.
6. **`uv run mypy --strict packages/docintel-generate/`:** Success: no issues found in 3 source files.

## PROMPT_VERSION_HASH Transition Plan

| Commit | `PROMPT_VERSION_HASH` | What changed |
|--------|----------------------|--------------|
| 90e0409 (Task A — initial) | (replaced — see below) | Initial `SYNTHESIS_PROMPT` body had line-wrapped refusal sentinel (Rule 1 bug caught by behavior assertion). |
| 90e0409 (Task A — final, after Rule 1 fix) | `dab1bcf7379f` | `SYNTHESIS_PROMPT` rule 3 reformatted to keep refusal sentinel on one line. |
| 11e8d59 (Task B) | `dab1bcf7379f` (unchanged) | parse.py + __init__.py re-exports — no prompt-body edits. |
| 0eefc4a (Task C) | `dab1bcf7379f` (unchanged) | xfail-marker sweep on test file only. |

**Expected future transitions:**
- Plan 06-05 (Wave 3, stub adapter `_CHUNK_RE` re-import retirement) — should NOT change `PROMPT_VERSION_HASH` (no prompt-body edits).
- Plan 06-06 (Wave 3, judge migration) — should NOT change `PROMPT_VERSION_HASH` if the judge migration consumes `JUDGE_PROMPT` verbatim (which is the plan's design). Any tweak to the judge prompt body during migration WOULD flip both `_JUDGE_HASH` and `PROMPT_VERSION_HASH`. Wave 3 commit message should note any such transition explicitly.
- Plan 06-07 (Wave 4, xfail-removal sweep) — should NOT change `PROMPT_VERSION_HASH` (test-only edits).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Refusal sentinel line-wrap in `SYNTHESIS_PROMPT` rule 3**
- **Found during:** Task A behavior assertion `assert 'I cannot answer this question from the retrieved 10-K excerpts.' in SYNTHESIS_PROMPT` fired.
- **Issue:** RESEARCH §Code Example 1 line 882-883 line-wrapped the embedded refusal sentinel ("...emit\nverbatim and ONLY this sentence: \"I cannot answer this question from the retrieved\n10-K excerpts.\""). The PLAN line 152 explicitly requires `the embedded quoted sentence MUST byte-match REFUSAL_TEXT_SENTINEL (i.e., the same 64-char string)` — but the line-wrap inserts a literal newline mid-sentinel. An LLM instructed to emit the literal sentence verbatim would either copy the newline (breaking `is_refusal()` byte-exact `startswith()` matching against the clean sentinel) or unwrap it heuristically (producing different bytes than the deterministic stub adapter — defeating the Pitfall 9 single-source-of-truth invariant).
- **Fix:** Reformatted rule 3 to keep the quoted sentence on one line ("(a single line, no line break)" phrasing makes the constraint explicit for the LLM too). Body length: 971 chars. SYNTHESIS_PROMPT now contains `'I cannot answer this question from the retrieved 10-K excerpts.'` as a contiguous byte-run.
- **Files modified:** `packages/docintel-generate/src/docintel_generate/prompts.py` (single edit in `SYNTHESIS_PROMPT`'s rule 3 body).
- **Commit:** 90e0409 (the edit happened during Task A pre-commit verification; the committed `prompts.py` already has the fix).

### Auth Gates

None — Plan 06-03 is pure module-creation; no SDK or API touchpoints.

## Plan Outputs

Per `<output>` section of the plan:

- **SYNTHESIS_PROMPT byte-length:** 971 (informational).
- **JUDGE_PROMPT byte-length:** 723 (informational).
- **REFUSAL_PROMPT byte-length:** 63 (= `REFUSAL_TEXT_SENTINEL`).
- **`PROMPT_VERSION_HASH` at Wave 1 commit time:** `dab1bcf7379f`. Will be re-computed at Wave 3 (Plan 06-06) if the judge migration tweaks `JUDGE_PROMPT` body bytes; the next SUMMARY should diff against this value and explicitly note any change.
- **Prompt-locality gate confirms both `prompts.py` AND `parse.py` allowlisted:** `bash scripts/check_prompt_locality.sh` exits 0; gate output is `"OK: no inline prompts outside allowlist"`.
- **`adapters/stub/llm.py:31` still contains the duplicate `_CHUNK_RE` definition:** confirmed via `grep -n '_CHUNK_RE' packages/docintel-core/src/docintel_core/adapters/stub/llm.py` — line 31 unchanged. Plan 06-05 retires it.

## Commits

| Hash      | Subject                                                                                        |
| --------- | ---------------------------------------------------------------------------------------------- |
| `90e0409` | feat(06-03): land canonical prompts.py with three named Final[str] prompts + PROMPT_VERSION_HASH (GEN-01, GEN-02) |
| `11e8d59` | feat(06-03): land parse.py with _CHUNK_RE + is_refusal helper + Wave-1 __init__ re-exports     |
| `0eefc4a` | test(06-03): early xfail removal — prompt_version_hash tests now pass                         |

## Self-Check: PASSED

**Files verified (all FOUND):**
- `packages/docintel-generate/src/docintel_generate/prompts.py`
- `packages/docintel-generate/src/docintel_generate/parse.py`
- `packages/docintel-generate/src/docintel_generate/__init__.py`
- `tests/test_prompt_version_hash.py`
- `.planning/phases/06-generation/06-03-SUMMARY.md`

**Commits verified (all FOUND in git log):**
- `90e0409` — feat(06-03): land canonical prompts.py with three named Final[str] prompts + PROMPT_VERSION_HASH (GEN-01, GEN-02)
- `11e8d59` — feat(06-03): land parse.py with _CHUNK_RE + is_refusal helper + Wave-1 __init__ re-exports
- `0eefc4a` — test(06-03): early xfail removal — prompt_version_hash tests now pass
