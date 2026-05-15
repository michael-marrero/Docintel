"""Plan 06-01 Wave 0 xfail scaffolds for D-17 GenerationResult Pydantic shape.

Covers VALIDATION.md row 06-04-* (D-17) — the Phase 6 → Phase 7/9/10
contract:

* test_generation_result_frozen — ``ConfigDict(frozen=True)`` raises
  ``pydantic.ValidationError`` on post-construction mutation (defense
  against shared-list corruption downstream).
* test_generation_result_extra_forbid — ``ConfigDict(extra="forbid")``
  raises on construction with unknown fields (defense against schema
  drift). The six D-17 fields are: ``text``, ``cited_chunk_ids``,
  ``refused``, ``retrieved_chunks``, ``completion``,
  ``prompt_version_hash``.

Both tests are xfail-strict-marked because ``GenerationResult`` does not
yet live in ``docintel_core.types`` at Wave 0. The in-function
``from docintel_core.types import GenerationResult`` raises ImportError
→ pytest counts this as the expected failure under xfail(strict=True).
Plan 06-04 adds ``GenerationResult`` to ``docintel_core.types`` (per
D-17's home: it lives in core so Phase 7 imports without depending on
``docintel-generate``) and these xfails flip to passing.

Analogs:
* ``tests/test_retrieved_chunk_schema.py`` (full file, 99 lines) —
  Phase 5 D-03 ``RetrievedChunk`` analog; same Pydantic-frozen +
  extra=forbid test pattern; same ``_ok_payload()`` helper convention.
* ``packages/docintel-core/src/docintel_core/types.py`` ``RetrievedChunk``
  — sibling shape Phase 6 D-17 mirrors.
* 06-PATTERNS.md §"ConfigDict(extra=forbid, frozen=True) for shared
  contracts" lines 928-939.
"""

from __future__ import annotations

import pytest


def _ok_payload() -> dict:
    """Canonical D-17 6-field payload — used across every test in this file.

    ``retrieved_chunks=[]`` and ``completion=None`` model the hard-refusal
    path (Step B of D-15): the LLM was not called so ``completion`` is
    None; no chunks retrieved so the list is empty. These two values are
    independently valid for the GenerationResult contract — the schema
    tests assert the Pydantic v2 invariants on a representative payload,
    not the semantic refusal logic (which Plan 06-04 ships alongside the
    Generator).
    """
    return {
        "text": "answer text",
        "cited_chunk_ids": ["AAPL-FY2024-Item-1A-007"],
        "refused": False,
        "retrieved_chunks": [],
        "completion": None,
        "prompt_version_hash": "abcdef012345",
    }


def test_generation_result_frozen() -> None:
    """D-17 — Pydantic frozen=True; downstream callers must not mutate.

    Phase 7's ``Answer`` wrapper consumes ``GenerationResult``; Phase 9
    metrics aggregate over a list of them; Phase 13's UI renders citations
    from them. ``frozen=True`` prevents any of those phases from
    accidentally mutating a shared instance (defense against shared-list
    corruption — Phase 5 D-03 ``RetrievedChunk`` precedent).
    """
    from docintel_core.types import GenerationResult
    from pydantic import ValidationError

    gr = GenerationResult(**_ok_payload())
    with pytest.raises(ValidationError):
        gr.refused = True  # type: ignore[misc]


def test_generation_result_extra_forbid() -> None:
    """D-17 — extra='forbid' rejects unknown fields on construction.

    Defense against schema drift: a future plan that adds a debug field
    to ``GenerationResult`` must update the model explicitly; passing an
    unknown field at construction time raises ``pydantic.ValidationError``.
    Phase 5 D-03 ``RetrievedChunk`` precedent — keeps the public shape
    minimal and grep-able.
    """
    from docintel_core.types import GenerationResult
    from pydantic import ValidationError

    payload = _ok_payload()
    payload["extra_field"] = "x"  # not on the D-17 6-field shape
    with pytest.raises(ValidationError):
        GenerationResult(**payload)
