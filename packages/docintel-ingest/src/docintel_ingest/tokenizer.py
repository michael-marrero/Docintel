"""Lazy-loaded BGE tokenizer singleton.

D-10: ``chunk.py`` counts tokens with the EXACT same tokenizer Phase 4's
      embedder will use (``BAAI/bge-small-en-v1.5``, 512-token cap,
      ``BertTokenizer`` class). This makes Phase 5's silent-truncation
      canary a real test instead of a bet against tokenizer drift.

Pitfall 3: revision is pinned to a 40-char SHA so re-runs across machines
      and across calendar months produce byte-identical chunk boundaries.
      Without this pin, ``AutoTokenizer.from_pretrained()`` defaults to the
      ``main`` branch and any future ``tokenizer.json`` refresh on the HF
      hub breaks ING-04 byte-identity silently. RESEARCH.md line 466
      verified the SHA against the HF tree listing on 2026-05-12.

Pitfall 9: ``from transformers import AutoTokenizer`` lives INSIDE
      ``get_bge_tokenizer()`` (NOT at module top) so
      ``docintel-ingest --help`` cold-start stays well under the 5-second
      budget. Importing transformers at module top triggers a torch
      import (~2-3s) that would regress
      ``tests/test_ingest_cli.py::test_help_latency_under_5s`` and
      ``::test_no_torch_import_on_help``. The ``TYPE_CHECKING`` guard
      around the ``PreTrainedTokenizerBase`` annotation is the standard
      Python idiom for "type hint that requires a heavy import" — mypy
      still type-checks the return annotation, but the runtime never
      imports transformers at module load.

Pitfall 10 defense in depth: the ``assert tok.model_max_length == 512``
      check inside ``get_bge_tokenizer()`` fails loudly if HF ever
      reconfigures the model with a different cap (a different failure
      mode from the revision pin — e.g. a config-only tweak that doesn't
      change the SHA we pin). The Phase 5 silent-truncation canary
      depends on this 512 cap being structurally true at chunk time.

The first call to ``get_bge_tokenizer()`` pays the ~150ms tokenizer-load
cost (and downloads ~944 KB to ``~/.cache/huggingface/hub/`` if the
revision isn't already cached). Subsequent calls hit the
``@lru_cache(maxsize=1)`` and return immediately.

No network calls outside the first ``from_pretrained`` HF-hub fetch.
``check_ingest_wraps.sh`` does NOT flag this file because its
``SDK_PATTERNS`` match the sec-edgar-downloader API only — not
``AutoTokenizer.from_pretrained(...)``. No ``@retry`` decorator is added
here per the project rule (loud-fail discipline; a transient
``from_pretrained`` failure should surface immediately rather than be
papered over).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase

# Two-logger pattern (SP-3) — symmetry with embedder_bge.py / fetch.py /
# normalize.py. tokenizer.py has no tenacity-wrapped retry call sites today
# (the from_pretrained call is loud-fail by design) so ``_retry_log`` is
# unused at module level; keep the binding for grep-symmetry with peers.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)

BGE_TOKENIZER_NAME = "BAAI/bge-small-en-v1.5"
# Pitfall 3: 40-char SHA pinning the exact tokenizer.json revision.
# Verified at https://huggingface.co/BAAI/bge-small-en-v1.5/tree/main as of
# 2026-05-12 (RESEARCH.md lines 465-466). MANIFEST.json (Wave 5) records
# this value as ``tokenizer.revision_hash`` and a CI test
# (tests/test_chunk_idempotency.py::test_manifest_hashes_match) asserts
# the source-code constant equals the manifest value.
BGE_TOKENIZER_REVISION = "982532469af0dff5df8e70b38075b0940e863662"


@lru_cache(maxsize=1)
def get_bge_tokenizer() -> PreTrainedTokenizerBase:
    """Singleton ``AutoTokenizer`` for ``BAAI/bge-small-en-v1.5`` (revision-pinned).

    Pitfall 3: revision pin makes chunk boundaries byte-identical across
    machines and HF-hub updates. Pitfall 9: lazy ``transformers`` import
    means ``docintel-ingest --help`` never pays the torch import cost.
    Pitfall 10: the ``model_max_length == 512`` assertion is defense in
    depth against a config-only tokenizer change that doesn't bump the
    revision SHA we pin.

    First call: downloads ~944 KB to ``~/.cache/huggingface/hub/`` if the
    revision isn't already cached locally (offline runs after the first
    invocation never hit the network). Logs a structured
    ``bge_tokenizer_loaded`` event with the pinned revision so reviewers
    can audit which version produced a given chunk set.

    Subsequent calls return the cached singleton — the
    ``@lru_cache(maxsize=1)`` makes the per-call cost effectively zero.

    Returns:
        The ``PreTrainedTokenizerBase`` subclass (in practice
        ``BertTokenizer``) loaded for BGE-small-en-v1.5 at the pinned
        revision. ``from __future__ import annotations`` (PEP 563)
        keeps the annotation lazy at runtime, so ``transformers`` is
        only imported when ``get_bge_tokenizer()`` actually runs —
        ``TYPE_CHECKING`` exposes the symbol to mypy without paying the
        runtime import.
    """
    # Lazy — torch import cost (~2-3s) happens HERE on the first call,
    # NOT at module top. Pitfall 9 keeps ``docintel-ingest --help`` fast.
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        BGE_TOKENIZER_NAME,
        revision=BGE_TOKENIZER_REVISION,
    )
    # Pitfall 10 defense in depth: if HF ever ships a tokenizer config
    # change that drops ``model_max_length`` below 512, the chunker's
    # HARD_CAP_TOKENS=500 margin no longer leaves room for [CLS]/[SEP]
    # and silent truncation could re-enter at retrieval time. Fail
    # loudly here so the regression surfaces at chunk time, not at
    # Phase 5 canary time (when the failure mode is much harder to
    # localize).
    assert tok.model_max_length == 512, (
        f"unexpected model_max_length: {tok.model_max_length} "
        f"(expected 512 for {BGE_TOKENIZER_NAME}@{BGE_TOKENIZER_REVISION})"
    )
    log.info(
        "bge_tokenizer_loaded",
        name=BGE_TOKENIZER_NAME,
        revision=BGE_TOKENIZER_REVISION,
        model_max_length=tok.model_max_length,
        tokenizer_class=tok.__class__.__name__,
    )
    return tok


def count_tokens(text: str) -> int:
    """Token count excluding ``[CLS]`` / ``[SEP]`` (``add_special_tokens=False``).

    Used by ``chunk.py`` to enforce D-11's HARD_CAP_TOKENS=500 (under
    BGE's 512 cap to leave a 12-token margin for special tokens and any
    tokenizer surprise). Counting content tokens only — the special
    tokens are appended at embedding time by the SentenceTransformer
    layer (Phase 4's BGEEmbedder.embed call), not here.

    Args:
        text: The string to tokenize.

    Returns:
        Count of content tokens (no ``[CLS]`` / ``[SEP]``). Cheap call
        path after the first ``get_bge_tokenizer()`` invocation pays
        the load cost.
    """
    return len(get_bge_tokenizer().encode(text, add_special_tokens=False))
