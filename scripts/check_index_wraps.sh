#!/usr/bin/env bash
# CI grep gate: every real adapter file that contains a Qdrant SDK
# call must also import tenacity (D-21 — ADP-06 analog for Phase 4).
#
# Refs:
#   .planning/phases/04-embedding-indexing/04-CONTEXT.md   D-21
#   .planning/phases/04-embedding-indexing/04-RESEARCH.md  §Pattern 6, §Pitfall 6
#
# Usage:
#   scripts/check_index_wraps.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/docintel-core/src/docintel_core/adapters/real
# (the directory where qdrant_dense.py lands in Plan 04-04). CI invokes this
# with no args; tests invoke it with an explicit fixture dir to exercise the
# negative case (e.g. tests/fixtures/missing_tenacity).
#
# SDK_PATTERNS: grep-extended regex matching the seven Qdrant SDK call sites
# plus the import token. RESEARCH §Pattern 6 lists the surface:
#   QdrantClient(        — the constructor
#   qdrant_client        — the import token
#   .upsert(             — incremental insert (alternative to .upload_points)
#   .upload_points(      — bulk insert (RESEARCH §Pitfall 5 — preferred over .upsert for large batches)
#   .query_points(       — replaces deprecated .search() (RESEARCH §State of the Art)
#   .get_collection(     — used by verify() to read points_count
#   .create_collection(  — collection creation in build()
#   .delete_collection(  — drop-and-recreate path (D-06 idempotency)
#
# DELIBERATELY: header comments inline the SDK_PATTERNS literals because the
# gate scans `packages/docintel-core/src/docintel_core/adapters/real`, NOT
# `scripts/`; the script's own source cannot false-positive itself.
#
# If a future wave introduces a new Qdrant SDK call surface, update
# SDK_PATTERNS here.
#
# Exit codes:
#   0 — all files with Qdrant SDK calls also import tenacity
#       (or no such files found — vacuous pass)
#   1 — at least one file has Qdrant SDK calls but no
#       'from tenacity import'
set -euo pipefail

INDEX_DIR="${1:-packages/docintel-core/src/docintel_core/adapters/real}"
PROBLEM=0

SDK_PATTERNS='QdrantClient(\|qdrant_client\|\.upsert(\|\.upload_points(\|\.query_points(\|\.get_collection(\|\.create_collection(\|\.delete_collection('

for f in $(grep -rl "$SDK_PATTERNS" "$INDEX_DIR" --include="*.py" --include="*.py.example" 2>/dev/null); do
    if ! grep -q "from tenacity import" "$f"; then
        echo "FAIL: $f contains SDK call(s) but no 'from tenacity import'"
        PROBLEM=1
    fi
done

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: all real adapter files with qdrant_client calls have tenacity imports"
fi

exit "$PROBLEM"
