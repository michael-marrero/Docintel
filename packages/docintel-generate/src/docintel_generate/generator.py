"""Phase 6 query-time generator. Composes Retriever + LLMClient into one .generate() seam.

Phase 6 D-15: a single ``Generator.generate(query, k) -> GenerationResult``
callable that runs the 5-step pipeline end-to-end. The pipeline order is
non-negotiable (Steps A..E — 06-CONTEXT.md D-15 + 06-RESEARCH.md Pattern 1
lines 296-435):

  A. retrieval — ``self._retriever.search(query, k=k)``; timed.
  B. hard zero-chunk refusal — if ``retrieved == []``, emit
     ``generator_refused_zero_chunks`` structlog warning, return
     ``GenerationResult(text=REFUSAL_TEXT_SENTINEL, refused=True,
     completion=None, ...)`` WITHOUT calling the LLM (saves a call + cost).
  C. format + LLM call — build the D-14 ``<context>`` user-prompt block,
     call ``self._bundle.llm.complete(prompt=user_prompt, system=
     SYNTHESIS_PROMPT)``; timed.
  D. citation parse + hallucination drop + refusal detect — extract every
     ``[chunk_id]`` token via ``_CHUNK_RE.findall(completion.text)``,
     de-duplicate preserving first-occurrence order, validate against
     ``{c.chunk_id for c in retrieved}``, DROP hallucinated IDs and emit
     one ``generator_hallucinated_chunk_id`` structlog warning per
     offending ID (D-13 step 4 + CD-07). ``is_refusal(completion.text)``
     sets the ``refused`` flag post-hoc.
  E. telemetry + return — emit ONE ``generator_completed`` structlog INFO
     line with the 15 D-16 fields (query_tokens, n_chunks_retrieved,
     n_chunks_cited, refused, prompt_version_hash, synthesis_hash,
     refusal_hash, judge_hash, prompt_tokens, completion_tokens, cost_usd,
     retrieval_ms, generation_ms, total_ms, model); return the
     ``GenerationResult``.

CD-04 inheritance: this module composes already-wrapped
``bundle.llm.complete()`` and adds NO new tenacity wraps. The CI grep gate
``scripts/check_adapter_wraps.sh`` is unchanged by Phase 6 — there are no
new SDK call sites in ``docintel-generate``. The Phase 2 D-18 adapter-layer
tenacity decoration owns retry policy; double-wrapping here would create
retry storms.

FND-11: ``cfg`` is consumed by the factory ``make_generator(cfg)``; this
module does NOT read environment variables. The factory composes
``make_adapters(cfg)`` + ``make_retriever(cfg)`` and constructs
``Generator(bundle, retriever)``.

CD-03: eager-stash of ``bundle`` + ``retriever`` references in
``__init__``. No on-disk state load; LLM SDK init is deferred lazy by
AnthropicAdapter._get_client (commit 9ec4d36). Mirrors Retriever's
shape but Retriever-specific concerns (``_load_chunk_map``, query
truncation, MANIFEST cardinality check, ``_CLAUDE_MD_HARD_GATE``)
deliberately do NOT appear here — they are Phase 5 invariants enforced
upstream.

Pitfall 9 single-source-of-truth: ``REFUSAL_TEXT_SENTINEL`` is imported
from ``docintel_core.types``; this module never redefines it. The stub
LLM adapter (Plan 06-05) imports the same constant. Import direction is
strictly ``docintel-generate → docintel-core``; never the reverse.
"""

from __future__ import annotations

import time

import structlog
from docintel_core.adapters.types import AdapterBundle
from docintel_core.types import REFUSAL_TEXT_SENTINEL, GenerationResult, RetrievedChunk
from docintel_retrieve.retriever import Retriever

from docintel_generate.parse import _CHUNK_RE, is_refusal
from docintel_generate.prompts import (
    _JUDGE_HASH,
    _REFUSAL_HASH,
    _SYNTHESIS_HASH,
    PROMPT_VERSION_HASH,
    SYNTHESIS_PROMPT,
)

# Single structlog logger — no tenacity in this module (CD-04). The SP-3 two-logger
# pattern (_retry_log + log) is intentionally NOT applied; the dead _retry_log
# placeholder would be misleading here since this module composes already-wrapped
# adapter calls and adds zero new SDK call sites.
log = structlog.stdlib.get_logger(__name__)


class Generator:
    """End-to-end query pipeline: retrieval → LLM synthesis → citation validation.

    D-15 single seam. Phase 7 wraps ``.generate()`` into Answer; Phase 9
    eval harness calls per-question; Phase 10 ablation reports diff fields
    across runs; Phase 11 swaps the bundle for ablations (NullReranker,
    NullBM25Store) without touching this class; Phase 13 FastAPI injects
    the Generator via dependency-injection lru-cache.

    Analog: ``packages/docintel-retrieve/src/docintel_retrieve/retriever.py``
    ``Retriever.search`` — same structural shape (eager-stash in __init__,
    one public method running a fixed-order pipeline, single structlog
    telemetry line at the end). Different concerns: no on-disk state,
    no token-overflow defense (Phase 5 enforced upstream), no query
    truncation (Retriever did it).

    CD-03 eager-stash: ``Generator.__init__(bundle, retriever)`` just
    stashes the two references. The Retriever's chunk-map eager load
    already paid the corpus-load cost; the LLM SDK init is deferred
    lazy in the real-mode adapter (commit 9ec4d36).
    """

    def __init__(self, bundle: AdapterBundle, retriever: Retriever) -> None:
        """Stash the AdapterBundle + Retriever references.

        Args:
            bundle:    AdapterBundle from ``make_adapters(cfg)`` — carries
                       ``embedder``, ``reranker``, ``llm``, ``judge``.
                       Generator consumes ``bundle.llm`` only; the other
                       three are owned by the Retriever.
            retriever: Retriever from ``make_retriever(cfg)`` — its
                       ``.search(query, k)`` is the Step A call site.
        """
        self._bundle = bundle
        self._retriever = retriever

    def generate(self, query: str, k: int = 5) -> GenerationResult:
        """One callable, end-to-end. See module docstring for the 5-step pipeline.

        Args:
            query: Raw user query — Retriever owns truncation per D-11; this
                method passes through verbatim. ``len(query.split())`` is
                used for the ``query_tokens`` telemetry field (whitespace
                tokenisation matches Retriever's stub-embedder count for
                consistency in stub mode; real mode reports BGE WordPiece
                count in retriever's own telemetry line, not this one).
            k:     Number of final results to request from Retriever.
                Defaults to 5 (matches Retriever ``TOP_K_FINAL`` per D-06).

        Returns:
            ``GenerationResult`` with the six D-17 fields. On hard refusal
            (Step B), ``text == REFUSAL_TEXT_SENTINEL`` and ``completion
            is None``. On LLM-driven refusal (Step D ``is_refusal(text)``),
            ``refused=True`` BUT ``completion is not None`` (the LLM was
            actually called).
        """
        t_total_start = time.perf_counter()

        # Step A — retrieval. Retriever owns query normalization (D-11), BM25+dense
        # retrieval (D-05), RRF fusion (D-07), top-M rerank (D-09), and emits its
        # own ``retriever_search_completed`` telemetry. Generator just consumes
        # the result list.
        t_retr_start = time.perf_counter()
        retrieved = self._retriever.search(query, k=k)
        retrieval_ms = (time.perf_counter() - t_retr_start) * 1000

        # Step B — hard zero-chunk refusal (skip LLM, save a call + cost).
        # Phase 9 MET-03 (faithfulness rate) counts this path via the
        # ``generator_refused_zero_chunks`` structlog event.
        if not retrieved:
            log.warning(
                "generator_refused_zero_chunks",
                query_tokens=len(query.split()),
            )
            result = GenerationResult(
                text=REFUSAL_TEXT_SENTINEL,
                cited_chunk_ids=[],
                refused=True,
                retrieved_chunks=[],
                completion=None,
                prompt_version_hash=PROMPT_VERSION_HASH,
            )
            self._emit_completed(
                query,
                result,
                retrieval_ms,
                0.0,
                (time.perf_counter() - t_total_start) * 1000,
            )
            return result

        # Step C — format the D-14 user-prompt and call the LLM. The LLM call is
        # already tenacity-wrapped at the adapter layer (Phase 2 D-18); CD-04
        # forbids a second wrap layer here.
        user_prompt = self._format_user_prompt(query, retrieved)
        t_gen_start = time.perf_counter()
        completion = self._bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)
        generation_ms = (time.perf_counter() - t_gen_start) * 1000

        # Step D — citation parse + hallucination drop + refusal detect.
        # _CHUNK_RE matches every [chunk_id] bracket token in the response;
        # we de-duplicate preserving first-occurrence order; validate every
        # cited chunk_id against the retrieved set; DROP hallucinated IDs
        # (LLM invented a chunk_id not in the prompt context) with a
        # structlog warning per offending ID (CD-07). Anti-pattern (per
        # 06-RESEARCH.md line 675): do NOT strip the hallucinated bracket
        # text from completion.text — that hides faithfulness regressions
        # from Phase 9 MET-04.
        raw_ids = _CHUNK_RE.findall(completion.text)
        retrieved_id_set = {c.chunk_id for c in retrieved}
        cited_chunk_ids: list[str] = []
        seen: set[str] = set()
        for cid in raw_ids:
            if cid in retrieved_id_set:
                if cid not in seen:
                    cited_chunk_ids.append(cid)
                    seen.add(cid)
            else:
                log.warning(
                    "generator_hallucinated_chunk_id",
                    chunk_id=cid,
                    query_tokens=len(query.split()),
                    model=completion.model,
                )

        # Post-hoc refusal detection — D-15 Step D. The LLM may emit the
        # canonical sentinel verbatim when it recognises the retrieved chunks
        # do not answer the question (more impressive failure mode than the
        # Step B hard-floor; says "the LLM is grounded, not just templating").
        refused = is_refusal(completion.text)

        result = GenerationResult(
            text=completion.text,
            cited_chunk_ids=cited_chunk_ids,
            refused=refused,
            retrieved_chunks=retrieved,
            completion=completion,
            prompt_version_hash=PROMPT_VERSION_HASH,
        )

        # Step E — telemetry + return.
        self._emit_completed(
            query,
            result,
            retrieval_ms,
            generation_ms,
            (time.perf_counter() - t_total_start) * 1000,
        )
        return result

    def _format_user_prompt(self, query: str, retrieved: list[RetrievedChunk]) -> str:
        """Build the D-14 ``<context>``-block user prompt.

        Format (locked per 06-CONTEXT.md D-14):

            <context>
            [chunk_id: AAPL-FY2024-Item-1A-018 | company: AAPL | fiscal_year: 2024 | section: Item 1A]
            <chunk.text>
            ---
            [chunk_id: NVDA-FY2024-Item-7-042 | company: NVDA | fiscal_year: 2024 | section: Item 7]
            <chunk.text>
            ---
            </context>

            Question: <query>

        The ``[chunk_id: ... | company: ... | fiscal_year: ... | section: ...]``
        header gives the LLM the exact bracket token to cite per the
        SYNTHESIS_PROMPT rule. The Pitfall 10 comparative-question
        structuring guidance lives in the SYNTHESIS_PROMPT (not here) —
        this method only formats, it does NOT prescribe.
        """
        lines = ["<context>"]
        for c in retrieved:
            lines.append(
                f"[chunk_id: {c.chunk_id} | company: {c.ticker} | "
                f"fiscal_year: {c.fiscal_year} | section: {c.item_code}]"
            )
            lines.append(c.text)
            lines.append("---")
        lines.append("</context>")
        lines.append("")
        lines.append(f"Question: {query}")
        return "\n".join(lines)

    def _emit_completed(
        self,
        query: str,
        result: GenerationResult,
        retrieval_ms: float,
        generation_ms: float,
        total_ms: float,
    ) -> None:
        """Emit the single ``generator_completed`` structlog INFO line per D-16.

        15 named fields, exact ordering:

        1. query_tokens — whitespace-tokenised count of the raw query.
        2. n_chunks_retrieved — len(result.retrieved_chunks).
        3. n_chunks_cited — len(result.cited_chunk_ids) AFTER hallucination drop.
        4. refused — True iff Step B hard-refusal OR Step D ``is_refusal(text)``.
        5-8. prompt_version_hash, synthesis_hash, refusal_hash, judge_hash —
             from Plan 06-03 prompts.py. Per-prompt hashes enable Phase 11
             ablation reports to spot localised drift (e.g., only SYNTHESIS_PROMPT
             changed → only synthesis_hash differs).
        9-11. prompt_tokens, completion_tokens, cost_usd — sourced from
             ``result.completion`` (or zeros on hard refusal where
             ``completion is None``).
        12-14. retrieval_ms, generation_ms, total_ms — rounded to 2 decimals
             to match Phase 5 retriever_search_completed formatting.
        15. model — ``completion.model`` or ``"stub-refusal"`` on hard refusal.

        Phase 9 MET-05 reads ``cost_usd`` + ``total_ms``; Phase 9 MET-03
        reads ``refused``; Phase 11 ablation reports diff fields across
        runs; Phase 12 binds ``trace_id`` automatically via ``contextvars``
        once OBS-01 lands.
        """
        comp = result.completion
        log.info(
            "generator_completed",
            query_tokens=len(query.split()),
            n_chunks_retrieved=len(result.retrieved_chunks),
            n_chunks_cited=len(result.cited_chunk_ids),
            refused=result.refused,
            prompt_version_hash=PROMPT_VERSION_HASH,
            synthesis_hash=_SYNTHESIS_HASH,
            refusal_hash=_REFUSAL_HASH,
            judge_hash=_JUDGE_HASH,
            prompt_tokens=comp.usage.prompt_tokens if comp else 0,
            completion_tokens=comp.usage.completion_tokens if comp else 0,
            cost_usd=comp.cost_usd if comp else 0.0,
            retrieval_ms=round(retrieval_ms, 2),
            generation_ms=round(generation_ms, 2),
            total_ms=round(total_ms, 2),
            model=comp.model if comp else "stub-refusal",
        )
