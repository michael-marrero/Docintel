"""Negative fixture for tests/test_prompt_locality.py::test_grep_gate_fails_on_violation.

This file intentionally contains an inline prompt-like string outside the
allowlist. The GEN-01 grep gate (scripts/check_prompt_locality.sh, Plan 06-02)
must flag this file with exit code 1.

DO NOT import this file or execute it — it is a static fixture only:

* pytest does NOT collect this file (lives under tests/fixtures/, not under
  a directory matching pytest's testpath; filename does not start with test_;
  no pytest-collectable construct inside).
* The constant below mirrors the ``NAME_PATTERN`` (`_[A-Z_]*PROMPT[A-Z_]*\\b`)
  and ``PHRASE_PATTERN`` substrings (``You are``, ``<context>``, ``cite``,
  ``chunk_id``) from 06-RESEARCH.md §Pattern 4 — the GEN-01 gate scans for
  exactly this shape outside the allowlist.

This fixture is the analog of ``tests/fixtures/missing_tenacity/qdrant_fake.py``
(Phase 4 negative-case fixture for the index-wrap grep gate).
"""

_INLINE_SYNTHESIS_PROMPT = """You are answering a question using ONLY the
retrieved 10-K excerpts in the <context> block below. Every factual sentence
must end with a [chunk_id] citation. Do not invent chunk_ids; only cite from
<context>."""
