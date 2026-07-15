#!/usr/bin/env bash
# CI grep gate: EMP-05 / D-06 / P-EMP-04.
# Real adapters must use the sanitizing before_sleep_safe wrapper, not
# tenacity's raw before_sleep_log. Two-sided:
#   (a) no raw before_sleep_log in adapters/real/
#       (raw use leaks API-key patterns in retry-path exception strings
#        into committed CI logs — see Phase 14 D-04/D-05/D-06).
#   (b) every @retry-using file imports before_sleep_safe from
#       docintel_core.adapters.real._logging (closes the "new adapter
#       lands with @retry( but no before_sleep param" gap structurally).
#
# Usage:
#   scripts/check_before_sleep_safe.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/docintel-core/src/docintel_core/adapters/real
# Pass a different directory (e.g., tests/fixtures/before_sleep_violations/)
# to test the negative case.
#
# Exit codes:
#   0 — no raw before_sleep_log found AND every @retry-using file imports
#       before_sleep_safe
#   1 — at least one violation (either side)
set -euo pipefail

REAL_ADAPTERS="${1:-packages/docintel-core/src/docintel_core/adapters/real}"
PROBLEM=0

# Side A (negative): grep for raw before_sleep_log must find nothing
if grep -rn "before_sleep_log" "$REAL_ADAPTERS" --include="*.py" 2>/dev/null; then
    echo "FAIL: raw before_sleep_log found in $REAL_ADAPTERS (P-EMP-04: API key leak surface)"
    echo "      use docintel_core.adapters.real._logging.before_sleep_safe instead"
    PROBLEM=1
fi

# Side B (positive): every file containing @retry( MUST import before_sleep_safe
for f in $(grep -rl "@retry(" "$REAL_ADAPTERS" --include="*.py" 2>/dev/null); do
    if ! grep -q "from \._logging import\|from docintel_core\.adapters\.real\._logging import" "$f" \
       || ! grep -q "before_sleep_safe" "$f"; then
        echo "FAIL: $f contains @retry( but does not import before_sleep_safe"
        PROBLEM=1
    fi
done

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: adapters/real/ uses before_sleep_safe and never raw before_sleep_log"
fi

exit "$PROBLEM"
