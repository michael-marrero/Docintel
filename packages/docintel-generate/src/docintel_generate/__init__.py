"""Phase 6 implementation — query-time generation.

Composes Phase 5 `Retriever` + Phase 2 `LLMClient` into a single
`Generator.generate(query, k) -> GenerationResult` seam.

See `docintel_generate.generator` for the orchestrator class;
`docintel_generate.prompts` for the canonical prompt home (GEN-01);
`docintel_generate.parse` for the regex + sentinel helpers.

Public surface is built up incrementally across Plans 06-03..06-04:
- Plan 06-03 adds SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT, PROMPT_VERSION_HASH re-exports.
- Plan 06-04 adds Generator, GenerationResult re-exports.

Wave 0 (this plan, 06-02) ships the skeleton only — no imports, empty `__all__`.
The submodules (`prompts`, `parse`, `generator`) do not yet exist; adding imports
here before they land would fail at import time.
"""

__all__: list[str] = []
