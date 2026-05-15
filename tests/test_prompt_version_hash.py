"""Plan 06-01 Wave 0 xfail scaffolds for GEN-02 prompt version hashes (D-08).

Covers VALIDATION.md row 06-03-* (GEN-02 + D-08) — the prompt-version-hash
contract that Phase 10 EVAL-02's report-manifest header and Phase 9 MET-*
metrics consume:

* test_hash_format — ``PROMPT_VERSION_HASH`` is a 12-char lowercase hex
  string (D-08 sha256-truncated-to-12 convention).
* test_hash_sensitivity — single-byte change to ``SYNTHESIS_PROMPT`` flips
  the per-prompt hash. Pitfall 3 defense: a regression that silently
  rewords a prompt without bumping the hash would let two ablation runs
  share the same hash but produce different outputs.
* test_per_prompt_hashes_exposed — the three per-prompt hashes
  ``_SYNTHESIS_HASH`` / ``_REFUSAL_HASH`` / ``_JUDGE_HASH`` are all 12-char
  hex AND mutually distinct (collision check); the
  ``generator_completed`` structlog line and any ablation reports source
  per-prompt hashes from these constants.

All three tests are xfail-strict-marked because
``docintel_generate.prompts`` does not exist at Wave 0. The in-function
``from docintel_generate.prompts import ...`` raises ImportError →
pytest counts this as the expected failure under xfail(strict=True).
Plan 06-03 ships ``packages/docintel-generate/src/docintel_generate/prompts.py``
with the four constants + the ``_h`` helper and these xfails flip to passing.

Analogs:
* ``tests/test_retrieved_chunk_schema.py:1-32`` (xfail-strict-with-reason
  pattern; in-function import → ImportError-as-xfail).
* 06-CONTEXT.md D-08 (`_h(s) = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]`).
* 06-PATTERNS.md §"Tests scaffolds" line 847 (analog assignment).
"""

from __future__ import annotations


def test_hash_format() -> None:
    """GEN-02 + D-08 — PROMPT_VERSION_HASH is a 12-char lowercase hex string.

    The Phase 10 EVAL-02 report-manifest header carries this single
    combined hash; CI greps for the hash to detect prompt-config drift
    across runs. The 12-char-lowercase-hex shape is locked so a malformed
    hash never lands in a manifest.
    """
    from docintel_generate.prompts import PROMPT_VERSION_HASH

    assert isinstance(
        PROMPT_VERSION_HASH, str
    ), f"D-08: PROMPT_VERSION_HASH must be str; got {type(PROMPT_VERSION_HASH).__name__}"
    assert (
        len(PROMPT_VERSION_HASH) == 12
    ), f"D-08: PROMPT_VERSION_HASH must be 12 chars; got len={len(PROMPT_VERSION_HASH)}"
    assert all(
        c in "0123456789abcdef" for c in PROMPT_VERSION_HASH
    ), f"D-08: PROMPT_VERSION_HASH must be lowercase hex; got {PROMPT_VERSION_HASH!r}"


def test_per_prompt_hashes_exposed() -> None:
    """GEN-02 + D-08 — per-prompt hashes exposed for ablation localisation.

    The Phase 6 D-16 ``generator_completed`` structlog line carries
    ``synthesis_hash`` / ``refusal_hash`` / ``judge_hash`` so a Phase 11
    ablation report can pinpoint which prompt changed across runs even
    when the combined ``PROMPT_VERSION_HASH`` flips. All three are 12-char
    hex; all three are mutually distinct (collision sanity check —
    SHA256-truncated-to-12 across distinct prompt bodies should never
    collide in practice).
    """
    from docintel_generate.prompts import _JUDGE_HASH, _REFUSAL_HASH, _SYNTHESIS_HASH

    for name, value in (
        ("_SYNTHESIS_HASH", _SYNTHESIS_HASH),
        ("_REFUSAL_HASH", _REFUSAL_HASH),
        ("_JUDGE_HASH", _JUDGE_HASH),
    ):
        assert isinstance(value, str), f"D-08: {name} must be str; got {type(value).__name__}"
        assert len(value) == 12, f"D-08: {name} must be 12 chars; got len={len(value)}"
        assert all(
            c in "0123456789abcdef" for c in value
        ), f"D-08: {name} must be lowercase hex; got {value!r}"
    # Distinctness — collision sanity check across the three prompts.
    distinct = {_SYNTHESIS_HASH, _REFUSAL_HASH, _JUDGE_HASH}
    assert len(distinct) == 3, (
        "D-08 + Pitfall 3: per-prompt hashes must be distinct; "
        f"_SYNTHESIS_HASH={_SYNTHESIS_HASH!r} _REFUSAL_HASH={_REFUSAL_HASH!r} "
        f"_JUDGE_HASH={_JUDGE_HASH!r}"
    )


def test_hash_sensitivity() -> None:
    """GEN-02 + D-08 + Pitfall 3 — single-byte change flips the hash.

    Re-applies the ``_h`` helper to the canonical ``SYNTHESIS_PROMPT``
    body and asserts the result equals ``_SYNTHESIS_HASH`` (round-trip
    sanity). Then applies ``_h`` to ``SYNTHESIS_PROMPT + "x"`` and asserts
    the result does NOT equal ``_SYNTHESIS_HASH`` — a one-byte change
    must flip the hash. Pitfall 3 defense: a silent reword without a
    hash bump would let two ablation runs share a manifest hash but
    produce different outputs.
    """
    from docintel_generate.prompts import _SYNTHESIS_HASH, SYNTHESIS_PROMPT, _h

    # Round-trip — _h(SYNTHESIS_PROMPT) must equal the module-level hash.
    assert (
        _h(SYNTHESIS_PROMPT) == _SYNTHESIS_HASH
    ), "D-08: _h(SYNTHESIS_PROMPT) must equal _SYNTHESIS_HASH at module-import time"
    # Sensitivity — a single-byte change must flip the hash.
    mutated = _h(SYNTHESIS_PROMPT + "x")
    assert mutated != _SYNTHESIS_HASH, (
        f"D-08 + Pitfall 3: _h must be sensitive to single-byte changes; "
        f"got _h(SYNTHESIS_PROMPT)={_SYNTHESIS_HASH!r} == _h(SYNTHESIS_PROMPT+'x')={mutated!r}"
    )
