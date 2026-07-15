"""Story 1.2 — schema Literal expansion is backward-compatible (AC-4 guard).

Adding "transcript"/"Q4" to the filing_type/fiscal_period Literals must NOT
change how existing 10-K/10-Q/8-K values validate — that's what keeps the
committed corpus byte-identical with no re-baseline. extra="forbid" still
rejects unknown values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docintel_core.types import Chunk
from pydantic import ValidationError

_GOLDEN = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "sample_transcript"
    / "aapl_CALL-Q1FY2024_chunks.jsonl"
)


def _a_chunk_dict() -> dict:
    return json.loads(_GOLDEN.read_text("utf-8").splitlines()[0])


def test_transcript_and_q4_validate() -> None:
    d = _a_chunk_dict()
    assert d["filing_type"] == "transcript"
    assert Chunk.model_validate(d).filing_type == "transcript"
    assert Chunk.model_validate({**d, "fiscal_period": "Q4"}).fiscal_period == "Q4"


def test_existing_filing_values_unchanged() -> None:
    d = _a_chunk_dict()
    for ft in ("10-K", "10-Q", "8-K"):
        assert Chunk.model_validate({**d, "filing_type": ft}).filing_type == ft
    for fp in ("FY", "Q1", "Q2", "Q3"):
        assert Chunk.model_validate({**d, "fiscal_period": fp}).fiscal_period == fp


def test_unknown_values_rejected() -> None:
    d = _a_chunk_dict()
    with pytest.raises(ValidationError):
        Chunk.model_validate({**d, "filing_type": "S-1"})
    with pytest.raises(ValidationError):
        Chunk.model_validate({**d, "fiscal_period": "H1"})
