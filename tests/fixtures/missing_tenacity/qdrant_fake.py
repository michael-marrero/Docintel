#
# Fixture for the index-wrap grep gate negative-case test (lives next to
# tests/test_index_wraps_gate.py — created in Plan 04-06).
#
# This file is INTENTIONALLY un-wrapped — it imports qdrant_client and calls
# client.upsert(...) WITHOUT a corresponding tenacity retry import.
# scripts/check_index_wraps.sh (Plan 04-06) must detect this pattern and
# exit non-zero. The positive-case test writes a sibling dummy.py with both
# the retry import AND a qdrant call site — the gate must accept that.
#
# DO NOT import this file or execute it — it is a static fixture only:
#
#   * pytest does NOT collect this file (lives under tests/fixtures/, not
#     under a directory matching pytest's testpath; filename does not start
#     with test_; no pytest-collectable construct inside).
#   * qdrant_client is NOT a runtime dep of any package today — the import
#     below would fail at runtime, which is fine because the file is read
#     by `grep`, not executed by Python.
#
# Listed in .gitleaks.toml allowlist as defense-in-depth (CD-09). No key
# shapes are present; the URL is the Qdrant docs default (RFC-style example).

from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
client.upsert(
    collection_name="docintel-dense-v1",
    points=[
        {
            "id": "00000000-0000-0000-0000-000000000000",
            "vector": [0.0] * 384,
            "payload": {"chunk_id": "AAPL-FY2024-Item-1A-007"},
        }
    ],
)
