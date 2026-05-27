#!/usr/bin/env bash
# CI grep gate: OBS-03 (Phase 12 D-06/D-07/D-08).
#
# Fails if a Python file under packages/*/src contains a bare `print(` call.
# Logs are JSON via structlog (FND-02); production code must not use print().
#
# Mirrors scripts/check_prompt_locality.sh structure (noqa escape + SCAN_DIR arg).
#
# Usage:
#   scripts/check_no_print.sh [SCAN_DIR]
#
# SCAN_DIR defaults to the src trees (packages/*/src). CI invokes with no args;
# tests invoke it with a fixture dir to exercise the negative case. The src-only
# scope is deliberate (D-06): scripts/ and tests/ legitimately print, and the
# Streamlit UI uses st.* — none of those live under packages/*/src.
#
# Per-line escape: append `# noqa: no-print` to silence a line.
# Outstanding exceptions: grep -rn 'noqa: no-print' packages/
#
# Exit codes:
#   0 — no bare print( outside the noqa escape
#   1 — at least one offending line
set -euo pipefail

# Default scan = every package's src tree (D-06: src only; not tests/ or scripts/).
# Using a glob expansion guarded for the no-match case.
if [ "$#" -ge 1 ]; then
    SCAN_DIRS=("$1")
else
    SCAN_DIRS=()
    for d in packages/*/src; do
        [ -d "$d" ] && SCAN_DIRS+=("$d")
    done
fi
PROBLEM=0

# Bare print( with a non-identifier / non-dot / non-backtick char (or
# start-of-line) in front, so pprint(, sprint(, obj.print( do NOT match — and
# neither do RST inline-literal mentions in docstrings/comments (``print(``),
# the false-positive class called out in 12-RESEARCH Pitfall 5. Portable across
# GNU+BSD grep (CI is Ubuntu; devs run macOS — the explicit char-class beats
# GNU-only \b).
PRINT_PATTERN='(^|[^A-Za-z0-9_.`])print\('

while IFS=: read -r file lineno _match; do
    [[ -z "$file" ]] && continue
    if grep -q '# noqa: no-print' <<<"$(sed -n "${lineno}p" "$file")"; then
        continue
    fi
    echo "FAIL: $file:$lineno contains a bare print( — use structlog (FND-02)"
    PROBLEM=1
done < <(grep -rnE --include='*.py' "$PRINT_PATTERN" "${SCAN_DIRS[@]}" 2>/dev/null || true)

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: no bare print( in packages/*/src"
fi

exit "$PROBLEM"
