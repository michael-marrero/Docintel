#!/usr/bin/env python3
"""Phase 14 ADR-014 / D-14: pre-run probe for an OpenAI-compatible (NIM) endpoint.

The real-eval's faithfulness judge sends
``response_format={"type":"json_schema","strict":true}``. If the judge model on
the configured endpoint does NOT honor strict JSON-schema, every verdict
silently degrades to the sentinel ``score=0`` (Pitfall 6) and faithfulness is
garbage-but-green. ADR-014 makes this probe a MANDATORY gate before any full
real-eval run against NIM is trusted.

What it does (no eval harness, no corpus — just two live calls):

1. **Generator smoke** — one tiny ``.complete()`` against ``DOCINTEL_OPENAI_MODEL``
   via ``DOCINTEL_OPENAI_BASE_URL``. Confirms the endpoint, key, and model id
   resolve, and prints token usage + cost (which is $0 on NIM free tier).
2. **Judge structured-output probe** — one ``.judge()`` against
   ``DOCINTEL_JUDGE_MODEL`` on a deliberately UNFAITHFUL prediction. A working
   strict-json_schema model returns a real verdict (non-sentinel). If the model
   ignores the schema, ``judge.py`` returns the sentinel and this probe FAILS
   loudly with exit code 2 — telling the operator to pick a different judge
   model or wire a fallback BEFORE burning eval budget.

Usage::

    # with the NIM env vars exported (see .env.example ADR-014 block):
    uv run python scripts/nim_probe.py
    .venv/bin/python scripts/nim_probe.py

Exit codes: 0 = both calls healthy; 1 = config/transport error; 2 = judge
returned the sentinel (strict json_schema NOT honored — do not trust eval).
"""

from __future__ import annotations

import sys

from docintel_core.adapters import make_adapters
from docintel_core.config import Settings

# The sentinel reasoning string emitted by judge.py on structured-output failure.
_SENTINEL_REASONING = "<deserialization failed>"


def main() -> int:
    cfg = Settings()

    print("=== NIM / OpenAI-compatible endpoint probe (ADR-014) ===")
    print(f"  llm_provider      = {cfg.llm_provider}")
    print(f"  llm_real_provider = {cfg.llm_real_provider}")
    print(f"  openai_base_url   = {cfg.openai_base_url or '(SDK default: api.openai.com)'}")
    print(f"  openai_model      = {cfg.openai_model}  (generator)")
    print(f"  judge_model       = {cfg.judge_model or '(none → Anthropic cross-provider judge)'}")
    print()

    if cfg.llm_provider != "real":
        print(
            "FAIL: DOCINTEL_LLM_PROVIDER must be 'real' to probe a live endpoint.", file=sys.stderr
        )
        return 1
    if cfg.openai_api_key is None:
        print(
            "FAIL: DOCINTEL_OPENAI_API_KEY is empty (put the nvapi-... key here).", file=sys.stderr
        )
        return 1

    try:
        bundle = make_adapters(cfg)
    except Exception as exc:  # pragma: no cover - config-time failure
        print(f"FAIL: could not build adapters: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # 1. Generator smoke ----------------------------------------------------
    print(f"[1/2] generator .complete() on {bundle.llm.name} ...")
    try:
        resp = bundle.llm.complete(
            prompt="Reply with exactly the word: OK",
            system="You are a terse assistant. Reply with a single word.",
        )
    except Exception as exc:
        print(f"FAIL: generator call errored: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"      text       : {resp.text!r}")
    print(
        f"      tokens      : prompt={resp.usage.prompt_tokens} completion={resp.usage.completion_tokens}"
    )
    print(f"      cost_usd    : {resp.cost_usd}  (0.0 expected on NIM free tier)")
    print(f"      latency_ms  : {resp.latency_ms:.0f}")
    print()

    # 2. Judge structured-output probe -------------------------------------
    # Deliberately unfaithful: the prediction claims a number the reference
    # does not support. A model that honors the schema should return a real
    # verdict (typically passed=False / low score). The point is NOT the
    # verdict's value — it's that we get a NON-sentinel verdict at all.
    print(f"[2/2] judge .judge() structured-output probe on {bundle.judge.name} ...")
    try:
        verdict = bundle.judge.judge(
            prediction="Revenue grew exactly 42% in fiscal 2023.",
            reference=["The 10-K states revenue was approximately flat year over year."],
            rubric="Score faithfulness of the prediction to the reference passages.",
        )
    except Exception as exc:
        print(f"FAIL: judge call errored: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"      score              : {verdict.score}")
    print(f"      passed             : {verdict.passed}")
    print(f"      reasoning          : {verdict.reasoning[:120]!r}")
    print(f"      unsupported_claims : {verdict.unsupported_claims}")
    print()

    if verdict.reasoning == _SENTINEL_REASONING:
        print(
            "FAIL (exit 2): judge returned the SENTINEL verdict — the model did NOT honor\n"
            "  strict json_schema structured output. Every eval verdict would silently be\n"
            "  score=0. Pick a different DOCINTEL_JUDGE_MODEL or wire a parser fallback\n"
            "  before running the real-eval. See ADR-014.",
            file=sys.stderr,
        )
        return 2

    print("PASS: both calls healthy and the judge honored strict json_schema.")
    print("      Safe to proceed with the real-eval run (ADR-014 gate cleared).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
