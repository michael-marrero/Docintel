"""Wave 0 scaffold — Pitfall 3 ``np.save`` byte-determinism canary.

Covers VALIDATION.md Per-Task Verification Map row for Pitfall 3 (``np.save``
on a float32 ndarray produces byte-identical bytes across two calls when numpy
is pinned). This is the cheap-and-loud canary that catches dense-store
non-determinism BEFORE the integration-level idempotency gate reveals it
indirectly (the integration gate would still flag the drift, but at higher cost
and with less actionable failure messaging).

Plan 04-05 committed a numpy-backed dense store that depends on this invariant;
Plan 04-07 Task 1 removed the former xfail marker so the canary now runs as a
hard test.

Analog: closest is ``tests/test_chunk_idempotency.py::test_chunks_byte_identical``
(shape only — run-twice-and-compare-bytes structure).

Reference: RESEARCH §Pitfall 3 lines 530-536 — the test vector is verbatim from
the research note.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def test_np_save_deterministic(tmp_path: Path) -> None:
    """Pitfall 3: ``np.save`` on a fixed float32 ndarray is byte-deterministic.

    Pin ``numpy==2.4.4`` and DO NOT use ``savez_compressed`` (zlib gzip headers
    are non-deterministic). The plain ``np.save`` format writes a magic-string
    header + version + header dict + array bytes — none of those contain
    timestamps or hostnames.
    """
    arr = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
    path_a = tmp_path / "a.npy"
    path_b = tmp_path / "b.npy"
    np.save(path_a, arr)
    np.save(path_b, arr)
    assert path_a.read_bytes() == path_b.read_bytes(), (
        "np.save is not byte-deterministic — Pitfall 3. "
        "Pin numpy==2.4.4 and DO NOT use savez_compressed."
    )
