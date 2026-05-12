"""Deterministic stub embedder -- 384-dim hash-based unit vectors.

Same text always yields the same vector; texts sharing tokens yield
measurably similar vectors (D-14). No randomness, no clock reads (ADP-07).
No retry wrapping -- stubs never make network calls, so tenacity is not
needed here. The CI grep gate for tenacity is scoped to adapters/real/ only.
"""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np

_DIM: Final[int] = 384
"""Output dimensionality -- matches BGE-small-en-v1.5 so dimension mismatches
surface in stub mode rather than being silently masked (D-14).
"""


def _text_to_vector(text: str) -> np.ndarray:
    """Deterministic 384-dim unit vector via token-bag SHA-256 hashing.

    Each whitespace-split token is hashed with SHA-256. The first two bytes
    of the digest select a bin index (mod 384); the next four bytes contribute
    a magnitude in [0, 1). All token contributions are accumulated, then
    unit-normalised. Texts sharing tokens produce measurably similar vectors.

    No randomness, no clock reads (ADP-07).

    Args:
        text: Input string to embed.

    Returns:
        float32 ndarray of shape (384,), unit-normalised.
        Empty text falls back to vec[0] = 1.0 (first bin).
    """
    tokens = text.lower().split()
    vec = np.zeros(_DIM, dtype=np.float32)
    for token in tokens:
        h = hashlib.sha256(token.encode()).digest()
        # First 2 bytes -> bin index mod DIM
        bin_idx = int.from_bytes(h[:2], "little") % _DIM
        # Next 4 bytes -> magnitude contribution in [0, 1)
        magnitude = int.from_bytes(h[2:6], "little") / (2**32 - 1)
        vec[bin_idx] += magnitude
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    else:
        # Empty text fallback: first bin = 1.0 (unit vector)
        vec[0] = 1.0
    return vec


class StubEmbedder:
    """Deterministic 384-dim embedder for stub/CI mode.

    Satisfies the Embedder Protocol structurally (no inheritance).
    Deterministic: identical inputs always produce identical outputs.
    No external dependencies.
    """

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "stub-embedder"

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return float32 array of shape (len(texts), 384).

        Args:
            texts: Batch of strings to embed. Empty list returns shape (0, 384).

        Returns:
            np.ndarray of shape (len(texts), 384), dtype float32.
        """
        if not texts:
            return np.zeros((0, _DIM), dtype=np.float32)
        return np.stack([_text_to_vector(t) for t in texts])
