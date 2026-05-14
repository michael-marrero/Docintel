#!/usr/bin/env bash
# CI grep gate: every docintel_ingest file that contains a sec-edgar-downloader
# call must also import tenacity (D-18 — ADP-06 analog for Phase 3).
#
# Usage:
#   scripts/check_ingest_wraps.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/docintel-ingest/src/docintel_ingest.
# CI invokes this with no args; tests invoke it with an explicit fixture dir
# to exercise the negative case (e.g. tests/fixtures/).
#
# SDK_PATTERNS: grep-extended regex matching the three forms of the
# sec-edgar-downloader call site in this package:
#   sec_edgar_downloader — the import
#   Downloader(          — the constructor
#   dl.get(              — the .get() method invocation
#
# Per CONTEXT.md D-03 there is exactly ONE such call site in docintel-ingest;
# the gate is structurally tight. If a future wave introduces a new sec-edgar-
# downloader API surface, update SDK_PATTERNS here.
#
# Exit codes:
#   0 — all files with sec-edgar-downloader calls also import tenacity
#       (or no such files found — vacuous pass)
#   1 — at least one file has sec-edgar-downloader calls but no
#       'from tenacity import'
set -euo pipefail

INGEST_DIR="${1:-packages/docintel-ingest/src/docintel_ingest}"
PROBLEM=0

SDK_PATTERNS='Downloader(\|dl\.get(\|sec_edgar_downloader'

for f in $(grep -rl "$SDK_PATTERNS" "$INGEST_DIR" --include="*.py" --include="*.py.example" 2>/dev/null); do
    if ! grep -q "from tenacity import" "$f"; then
        echo "FAIL: $f contains SDK call(s) but no 'from tenacity import'"
        PROBLEM=1
    fi
done

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: all ingest files with sec-edgar-downloader calls have tenacity imports"
fi

exit "$PROBLEM"
