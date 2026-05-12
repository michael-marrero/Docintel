#!/usr/bin/env bash
# CI grep gate: every real adapter file that contains an SDK call
# must also import tenacity (ADP-06, D-18).
#
# Usage:
#   scripts/check_adapter_wraps.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/docintel-core/src/docintel_core/adapters/real
# Pass a different directory (e.g., tests/fixtures/) to test the negative case.
#
# SDK_PATTERNS: grep-extended regex matching the four SDK call sites in this wave:
#   .messages.create    — Anthropic client
#   chat.completions.create — OpenAI client
#   .encode(            — SentenceTransformer
#   .predict(           — CrossEncoder
#
# If future waves add new SDK call sites in real/, update SDK_PATTERNS here.
#
# Exit codes:
#   0 — all files with SDK calls also import tenacity (or no SDK calls found)
#   1 — at least one file has SDK calls but no 'from tenacity import'
set -euo pipefail

REAL_ADAPTERS="${1:-packages/docintel-core/src/docintel_core/adapters/real}"
PROBLEM=0

SDK_PATTERNS='\.messages\.create\|chat\.completions\.create\|\.encode(\|\.predict('

for f in $(grep -rl "$SDK_PATTERNS" "$REAL_ADAPTERS" --include="*.py" --include="*.py.example" 2>/dev/null); do
    if ! grep -q "from tenacity import" "$f"; then
        echo "FAIL: $f contains SDK call(s) but no 'from tenacity import'"
        PROBLEM=1
    fi
done

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: all real adapter files with SDK calls have tenacity imports"
fi

exit "$PROBLEM"
