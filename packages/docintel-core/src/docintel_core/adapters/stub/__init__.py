"""Stub adapter implementations for docintel -- deterministic, offline-safe.

Stub adapters are deterministic: identical inputs always produce identical
outputs. They have no external dependencies (no network calls, no model
downloads, no API keys required) and require no retry wrapping since they
never make network calls (ADP-07).

This subpackage is the primary execution path for all CI runs (LLM_PROVIDER=stub
default). Wave 2 of Phase 2 fills this package with the four concrete stub
adapters:
  stub/embedder.py   -- StubEmbedder (hash-based 384-dim unit vectors, D-14)
  stub/reranker.py   -- StubReranker (cosine over same hash-based vectors, D-15)
  stub/llm_client.py -- StubLLMClient (templated synthesis from chunks, D-16)
  stub/llm_judge.py  -- StubLLMJudge (schema-check fraction grounded, D-17)
"""

from __future__ import annotations
