"""Phase 6 implementation — query-time generation.

Composes Phase 5 `Retriever` + Phase 2 `LLMClient` into a single
`Generator.generate(query, k) -> GenerationResult` seam.

See `docintel_generate.generator` for the orchestrator class;
`docintel_generate.prompts` for the canonical prompt home (GEN-01);
`docintel_generate.parse` for the regex + sentinel helpers.

Public surface is built up incrementally across Plans 06-03..06-04:
- Plan 06-03 adds SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT, PROMPT_VERSION_HASH re-exports.
- Plan 06-04 adds Generator, GenerationResult re-exports.

Wave 0 (Plan 06-02) shipped the skeleton only. Wave 1 (Plan 06-03) lands
`prompts` + `parse` submodules and re-exports the four public prompt names.
Wave 2 (Plan 06-04) will add `Generator` + `GenerationResult` re-exports.
"""

from docintel_core.types import GenerationResult

from docintel_generate.generator import Generator
from docintel_generate.prompts import (
    JUDGE_PROMPT,
    PROMPT_VERSION_HASH,
    REFUSAL_PROMPT,
    SYNTHESIS_PROMPT,
)

__all__ = [
    "JUDGE_PROMPT",
    "PROMPT_VERSION_HASH",
    "REFUSAL_PROMPT",
    "SYNTHESIS_PROMPT",
    "GenerationResult",
    "Generator",
]
