"""Wave 0 scaffold — Pattern 3 uuid5 stability + namespace pin tests.

Covers VALIDATION.md Per-Task Verification Map rows for Pattern 3
(``chunk_id_to_point_id`` is content-addressed via ``uuid.uuid5(NS, chunk_id)``
so the same chunk_id always maps to the same Qdrant point ID across builds and
machines; distinct chunk_ids produce distinct point IDs; the namespace UUID is
pinned at module level so the mapping is stable across dep bumps).

The CD-06 amendment in RESEARCH §Pattern 3 is the reason this test exists:
Qdrant rejects arbitrary string point IDs (`upsert(id="AAPL-FY2024-Item-1A-007")`
raises ``UnexpectedResponse 400`` per Qdrant maintainer #3461 / #5646). The fix
is mechanical and preserves the spirit of CD-06: derive a deterministic UUID
via uuid5 and store the human-readable chunk_id in ``point.payload["chunk_id"]``.

These tests are intentionally ``@pytest.mark.xfail(strict=False)`` until Plan
04-04 lands ``packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py``.
Plan 04-04 will commit the literal value of ``DOCINTEL_CHUNK_NAMESPACE`` into
this test in the same commit that pins it in the adapter. Plan 04-07 Task 1
removes the xfail markers.

Defensive: imports are wrapped in ``pytest.importorskip`` so the module
collects without ImportError even before Plan 04-04 lands the adapter.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.xfail(
    strict=False,
    reason="chunk_id_to_point_id lands in Plan 04-04; xfail removed in Plan 04-07",
)
def test_uuid5_deterministic() -> None:
    """Pattern 3: ``chunk_id_to_point_id`` is content-addressed — same input → same output."""
    qdrant_dense = pytest.importorskip("docintel_core.adapters.real.qdrant_dense")
    chunk_id_to_point_id = qdrant_dense.chunk_id_to_point_id

    a = chunk_id_to_point_id("AAPL-FY2024-Item-1A-007")
    b = chunk_id_to_point_id("AAPL-FY2024-Item-1A-007")
    assert a == b, (
        "chunk_id_to_point_id must be deterministic — uuid5 is content-addressed "
        "(Pattern 3 / CD-06 amendment)"
    )
    # Sanity: result is a valid UUID string (Qdrant rejects non-UUID strings).
    uuid.UUID(a)  # raises ValueError if not a valid UUID — see Pitfall 1


@pytest.mark.xfail(
    strict=False,
    reason="chunk_id_to_point_id lands in Plan 04-04; xfail removed in Plan 04-07",
)
def test_uuid5_collision_resistant() -> None:
    """Pattern 3: distinct chunk_ids must produce distinct point IDs."""
    qdrant_dense = pytest.importorskip("docintel_core.adapters.real.qdrant_dense")
    chunk_id_to_point_id = qdrant_dense.chunk_id_to_point_id

    a = chunk_id_to_point_id("AAPL-FY2024-Item-1A-007")
    b = chunk_id_to_point_id("AAPL-FY2024-Item-1A-008")
    assert a != b, (
        "uuid5 with distinct names must produce distinct UUIDs — collision would alias "
        "two chunks to the same Qdrant point (silent data loss)"
    )


@pytest.mark.xfail(
    strict=False,
    reason="DOCINTEL_CHUNK_NAMESPACE pinned in Plan 04-05; xfail removed in Plan 04-07",
)
def test_namespace_pinned() -> None:
    """Pattern 3: ``DOCINTEL_CHUNK_NAMESPACE`` is a stable module-level UUID constant.

    The namespace MUST be pinned so the chunk_id → point_id mapping is stable
    across machines and dep bumps. Plan 04-05 commits the literal value here
    AND in the adapter module in the same commit, so this assertion either
    matches both or fails fast on drift.

    The literal value is the output of
    ``uuid.uuid5(uuid.NAMESPACE_DNS, "docintel.dense.v1")`` computed once at
    Plan 04-05 land time. A grep-style cross-check in the Plan 04-05 acceptance
    criteria asserts that this ``expected_uuid`` matches the
    ``DOCINTEL_CHUNK_NAMESPACE = uuid.UUID("...")`` literal in the adapter
    source — both sides drift together or not at all.
    """
    qdrant_dense = pytest.importorskip("docintel_core.adapters.real.qdrant_dense")
    namespace = qdrant_dense.DOCINTEL_CHUNK_NAMESPACE

    assert isinstance(namespace, uuid.UUID), (
        f"DOCINTEL_CHUNK_NAMESPACE must be a uuid.UUID; got {type(namespace).__name__}"
    )
    # Plan 04-05 pinned literal — must match qdrant_dense.py DOCINTEL_CHUNK_NAMESPACE.
    expected_uuid = "576cc79e-7285-5efc-8e6e-b66d3e6f92ae"
    assert str(namespace) == expected_uuid, (
        f"DOCINTEL_CHUNK_NAMESPACE drift detected — expected {expected_uuid!r}, "
        f"got {str(namespace)!r}. Both qdrant_dense.py and this test must "
        "update together; a one-sided change breaks the chunk_id → point_id "
        "mapping across rebuilds and machines."
    )
