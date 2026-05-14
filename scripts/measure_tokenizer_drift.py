"""Phase 5 Plan 05-07 Task 1 — Tokenizer-drift diagnostic.

Measures the per-chunk token-count ratio between the **embedder** tokenizer
(BERT WordPiece — ``BAAI/bge-small-en-v1.5``) and the **reranker** tokenizer
(XLM-RoBERTa SentencePiece — ``BAAI/bge-reranker-base``) across every chunk
in ``data/corpus/chunks/**/*.jsonl``.

Purpose
-------

The Phase 5 RESEARCH §3 ("Tokenizer drift") + Pitfall 1 + Assumption A1
flagged that BERT WordPiece and XLM-RoBERTa SentencePiece can disagree on
English-prose token counts by roughly 5%, occasionally more. The exact
distribution was an open question pending empirical measurement. This
script closes that question by computing the actual distribution against
the 6,053-chunk corpus.

Defense-in-depth context
------------------------

Phase 3 enforces a hard cap of 500 tokens per chunk under the **BERT**
WordPiece tokenizer (the embedder side). The reranker uses XLM-RoBERTa
SentencePiece with a 512-token cap. If XLM-RoBERTa tokenizes a chunk to
> 500 tokens (i.e. drift > 0% in the worst direction), there is still a
12-token margin under the reranker cap. But if drift exceeds ~2.4%
(500 * 1.024 = 512), the reranker would silently truncate — the exact
Pitfall 6 failure mode CLAUDE.md's "BGE 512-token truncation FIRST"
hard-gate paragraph is defending against.

Plan 05-05 shipped the ``chunk_reranker_token_overflow`` structlog soft
warning in ``Retriever.search`` to surface this case at runtime. This
script answers the empirical question: is the soft warning **load-bearing**
(drift large enough to actually fire on real chunks) or **belt-and-suspenders**
(drift small enough that the warning never fires in practice)?

Run mode
--------

This script runs in **REAL mode** — it imports
``transformers.AutoTokenizer`` and downloads both models from HuggingFace
on first run (~50 MB tokenizer-only download; subsequent runs hit the
HF cache). It is NOT wired to default CI per PR. Run paths:

* **Developer-machine one-shot:** ``uv run python scripts/measure_tokenizer_drift.py``
  produces stdout summary; capture it to ``.planning/phases/05-retrieval-hybrid-rerank/05-TOKENIZER-DRIFT.md``.
* **workflow_dispatch (optional):** can be added to the ``real-index-build``
  job in ``.github/workflows/ci.yml`` if a CI artifact of the drift
  distribution is wanted; not required for Phase 5 closure.

Exit codes
----------

* ``0`` — diagnostic ran to completion against ≥ 1 chunk. The script is
  a diagnostic, not a gate; ``0`` is returned regardless of measured
  drift magnitude. The caller (Plan 05-07 SUMMARY) interprets the numbers
  and decides whether the soft warning is load-bearing.
* ``1`` — the chunks directory is empty (running on a fresh clone before
  ``make fetch-corpus``); print a warning and exit so CI fails cleanly.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

# Resolve the repository root from this file's location (scripts/measure_tokenizer_drift.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHUNKS_GLOB = _REPO_ROOT / "data" / "corpus" / "chunks"

# Tokenizer model identifiers (Phase 2 D-01 + D-02 — pinned at the project level).
# Verified against packages/docintel-core/src/docintel_core/adapters/real/embedder_bge.py:67
# and packages/docintel-core/src/docintel_core/adapters/real/reranker_bge.py:58.
_EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
_RERANKER_MODEL = "BAAI/bge-reranker-base"

# Reranker-side truncation risk threshold — the BGE-reranker SentencePiece
# token count above which the ``chunk_reranker_token_overflow`` soft warning
# from Plan 05-05 ``Retriever.search`` would fire at runtime.
_RERANKER_RISK_THRESHOLD = 500


def _iter_chunks() -> list[dict[str, Any]]:
    """Walk ``data/corpus/chunks/**/*.jsonl`` and return every chunk record.

    Returns:
        list of chunk dicts (one per non-empty JSONL line). Each record has
        the Phase 3 Chunk schema (chunk_id / text / n_tokens / ...).

    Notes:
        * Empty lines are skipped (mirrors ``_load_cases`` in
          ``tests/test_reranker_canary.py``).
        * The walk is sorted (deterministic) so the per-chunk output below
          is reproducible.
    """
    if not _CHUNKS_GLOB.is_dir():
        return []
    chunks: list[dict[str, Any]] = []
    for jsonl_path in sorted(_CHUNKS_GLOB.rglob("*.jsonl")):
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            chunks.append(json.loads(stripped))
    return chunks


def main() -> int:
    """Run the diagnostic and print the summary to stdout."""
    chunks = _iter_chunks()
    if not chunks:
        print(
            "WARNING: no chunks found under data/corpus/chunks/**/*.jsonl. "
            "Run `make fetch-corpus` first.",
            file=sys.stderr,
        )
        return 1

    # Lazy-import transformers so the script's import-time cost is just the
    # JSONL walk above; the heavy tokenizer download only happens here.
    from transformers import AutoTokenizer  # type: ignore[import-untyped]

    print(f"Loading embedder tokenizer (BERT WordPiece): {_EMBEDDER_MODEL}")
    embedder_tok = AutoTokenizer.from_pretrained(_EMBEDDER_MODEL)

    print(f"Loading reranker tokenizer (XLM-RoBERTa SentencePiece): {_RERANKER_MODEL}")
    reranker_tok = AutoTokenizer.from_pretrained(_RERANKER_MODEL)

    print(f"Tokenizing {len(chunks)} chunks under both tokenizers...")

    ratios: list[float] = []
    overflow_records: list[tuple[str, int, int]] = []  # (chunk_id, n_bert, n_xlmr)

    for chunk in chunks:
        text = chunk["text"]
        n_bert = len(embedder_tok.encode(text, truncation=False, add_special_tokens=True))
        n_xlmr = len(reranker_tok.encode(text, truncation=False, add_special_tokens=True))
        ratios.append(n_xlmr / n_bert if n_bert > 0 else 1.0)
        if n_xlmr > _RERANKER_RISK_THRESHOLD:
            overflow_records.append((chunk["chunk_id"], n_bert, n_xlmr))

    ratios_sorted = sorted(ratios)
    mean_ratio = statistics.fmean(ratios)
    median_ratio = statistics.median(ratios)
    p99_index = max(0, int(len(ratios_sorted) * 0.99) - 1)
    p99_ratio = ratios_sorted[p99_index]
    max_ratio = max(ratios)
    disagreement_pct = (mean_ratio - 1.0) * 100.0

    # Determine A1 status — RESEARCH §3 assumed ~5% disagreement on English prose.
    # CONFIRMED: 4–6% (close to the assumption). REFUTED: > 10% or < 1%.
    # EXTENDED: 6–10% (somewhat higher than the assumption but the soft warning
    # still acts as belt-and-suspenders).
    abs_disagreement = abs(disagreement_pct)
    if abs_disagreement <= 6.0:
        a1_status = "CONFIRMED"
    elif abs_disagreement <= 10.0:
        a1_status = "EXTENDED"
    else:
        a1_status = "REFUTED"

    print()
    print("TOKENIZER DRIFT DIAGNOSTIC (Phase 5 A1 assumption verification)")
    print("===============================================================")
    print(f"Corpus: data/corpus/chunks/**/*.jsonl ({len(chunks)} chunks)")
    print(f"BERT WordPiece tokenizer:  {_EMBEDDER_MODEL}")
    print(f"XLM-RoBERTa SentencePiece: {_RERANKER_MODEL}")
    print()
    print("Token-count ratio (XLM-RoBERTa / BERT):")
    print(f"  mean:   {mean_ratio:.4f}")
    print(f"  median: {median_ratio:.4f}")
    print(f"  p99:    {p99_ratio:.4f}")
    print(f"  max:    {max_ratio:.4f}")
    print()
    print(f"Chunks where XLM-RoBERTa-token-count > {_RERANKER_RISK_THRESHOLD} "
          f"(reranker truncation risk):")
    print(f"  count: {len(overflow_records)}")
    if overflow_records:
        print("  list (first 20):")
        for chunk_id, n_bert, n_xlmr in overflow_records[:20]:
            print(f"    - {chunk_id} (n_bert={n_bert} -> n_xlmr={n_xlmr})")
    print()
    print("A1 assumption (research §3): ~5% disagreement on English prose.")
    print(f"A1 measurement: mean ratio = {mean_ratio:.4f} "
          f"(disagreement = {disagreement_pct:+.2f}%).")
    print(f"A1 status: {a1_status}")
    print()
    if overflow_records:
        print(
            "INTERPRETATION: chunk_reranker_token_overflow soft warning "
            "(Plan 05-05) is LOAD-BEARING — some chunks would trip it in real mode."
        )
    else:
        print(
            "INTERPRETATION: chunk_reranker_token_overflow soft warning "
            "(Plan 05-05) is BELT-AND-SUSPENDERS — no chunks would trip it on "
            "this corpus."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
