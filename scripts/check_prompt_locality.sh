#!/usr/bin/env bash
# CI grep gate: GEN-01 (Phase 6 D-04).
#
# Fails if a Python file outside the allowlist contains an inline prompt-like
# string literal — either a constant whose name matches the prompt-identifier
# pattern, or a phrase whose body contains a prompt-like trigger word AND is
# longer than 80 characters (length filter cuts false positives — Pitfall 2).
#
# Mirrors check_adapter_wraps.sh / check_index_wraps.sh / check_ingest_wraps.sh
# structure verbatim (DRY-of-policy across the four CI grep gates).
#
# Usage:
#   scripts/check_prompt_locality.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/. CI invokes this with no args; tests invoke
# it with an explicit fixture dir to exercise the negative case (e.g.
# tests/fixtures/prompt_locality_violations/).
#
# Default allowlist (D-05):
#   - packages/docintel-generate/src/docintel_generate/prompts.py
#     (canonical prompt home — GEN-01)
#   - packages/docintel-generate/src/docintel_generate/parse.py
#     (regex + sentinel helpers — short literals only)
#   - packages/docintel-core/src/docintel_core/adapters/stub/llm.py
#     (pre-existing _STUB_REFUSAL + _CHUNK_RE per Phase 2 D-16 + Phase 6 D-12)
#   - packages/docintel-core/src/docintel_core/adapters/{real,stub}/judge.py
#     (pre-existing _JUDGE_SYSTEM_PROMPT placeholder per Phase 2; D-09 migrates
#     to prompts.py in Plan 06-06. The basename exclude is removed at that time.)
#   - packages/docintel-core/src/docintel_core/adapters/real/llm_{anthropic,openai}.py
#     (SDK fallback strings — ``system or "You are a helpful assistant."`` — are
#     adapter defaults invoked when caller passes no system prompt; out-of-scope
#     for GEN-01 which targets synthesis/refusal/judge prompts living in
#     docintel-generate.prompts.)
#   - tests/**, **/conftest.py, **/test_*.py
#     (test fixtures legitimately quote prompts for assertion)
#
# Per-line escape: append `# noqa: prompt-locality` to a line to silence the
# check for that line (mirrors `# noqa: E501` / `# type: ignore`). Outstanding
# exceptions grep-able via:
#   grep -rn 'noqa: prompt-locality' packages/
#
# Exit codes:
#   0 — no inline prompts outside allowlist (or no offenders found)
#   1 — at least one offending line found
set -euo pipefail

SCAN_DIR="${1:-packages/}"
PROBLEM=0

# Identifier-name detection: free-standing constants like _SOMETHING_PROMPT,
# _SYSTEM_INSTRUCTION_X, _Y_SYSTEM_PROMPT_Z. The leading ``\b`` anchor is
# load-bearing: without it the pattern also matches the trailing ``_PROMPT``
# substring inside non-underscore-prefixed identifiers like ``SYNTHESIS_PROMPT``
# (which appears in docstring text referencing the soon-to-land exports). With
# ``\b_`` the pattern only matches when the underscore is at a word boundary
# (preceded by whitespace, punctuation, or start-of-line) — i.e. the actual
# constant declaration or reference site.
NAME_PATTERN='\b_[A-Z_]*PROMPT[A-Z_]*\b|\b_[A-Z_]*INSTRUCTION[A-Z_]*\b|\b_[A-Z_]*SYSTEM_PROMPT\b'

# Phrase-content detection: prompt-trigger phrases. ``chunk_id`` is deliberately
# NOT in this set even though the plan-text RESEARCH §Pattern 4 includes it —
# ``chunk_id`` is the canonical domain term used pervasively in chunker,
# retriever, protocols, and qdrant/bm25 store docstrings and error messages
# (all of which legitimately exceed 80 chars). Triggering on ``chunk_id`` would
# produce a Wave 0 baseline that exits 1 against the existing codebase, which
# contradicts the plan's "exits 0 on canonical layout" acceptance. The remaining
# triggers (``You are``, ``Based on the``, XML-style tags, ``cite``, ``grounded``)
# are unambiguous prompt indicators per D-04 + D-10 (XML-style context blocks).
# Length filter ``[[ ${#match} -lt 80 ]] && continue`` further cuts FPs.
PHRASE_PATTERN='\b(You are|Based on the|<context>|<chunks>|cite|grounded)\b'

# Allowlist exclusions (D-05). ``--exclude-dir=tests`` covers tests/**. The
# per-file ``--exclude=<basename>`` entries work because each allowlisted
# basename is unique within its scan domain at Phase 6 (verified with
# ``find packages -name '<basename>'``). If a future plan adds a colliding
# basename, the gate needs ``--exclude-dir`` refinement at that time.
EXCLUDES=(
    "--exclude-dir=tests"
    "--exclude=conftest.py"
    "--exclude=test_*.py"
    "--exclude=prompts.py"
    "--exclude=parse.py"
    "--exclude=llm.py"
    "--exclude=judge.py"
    "--exclude=llm_anthropic.py"
    "--exclude=llm_openai.py"
)

# Loop 1 — Identifier-name violations.
while IFS=: read -r file lineno match; do
    [[ -z "$file" ]] && continue
    if grep -q '# noqa: prompt-locality' <<<"$(sed -n "${lineno}p" "$file")"; then
        continue
    fi
    echo "FAIL: $file:$lineno matches identifier pattern: $match"
    PROBLEM=1
done < <(grep -rnE --include='*.py' "${EXCLUDES[@]}" "$NAME_PATTERN" "$SCAN_DIR" 2>/dev/null || true)

# Loop 2 — Phrase-content violations (length-filtered).
while IFS=: read -r file lineno match; do
    [[ -z "$file" ]] && continue
    [[ ${#match} -lt 80 ]] && continue
    if grep -q '# noqa: prompt-locality' <<<"$(sed -n "${lineno}p" "$file")"; then
        continue
    fi
    echo "FAIL: $file:$lineno contains prompt-like phrase (>80 chars): $match"
    PROBLEM=1
done < <(grep -rnE --include='*.py' "${EXCLUDES[@]}" "$PHRASE_PATTERN" "$SCAN_DIR" 2>/dev/null || true)

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: no inline prompts outside allowlist"
fi

exit "$PROBLEM"
