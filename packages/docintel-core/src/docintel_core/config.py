"""Pydantic-settings module — the ONLY place in the codebase that reads env vars.

CI greps for direct env-reading calls (os dot environ / os dot getenv) outside this file
and fails on any match. This module is the single allowed reader; pydantic-settings handles
the actual env loading internally.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from env / .env file.

    Precedence: explicit kwargs > environment variables > .env file > defaults.

    Phase 1 scope: llm_provider literal, optional API keys, data dir, git SHA.
    Phase 2 will add the AdapterBundle factory that consumes llm_provider.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DOCINTEL_",
        extra="ignore",
        case_sensitive=False,
    )

    # Provider flip (FND-08). Default is `stub` everywhere — CI, .env.example, docker-compose.
    llm_provider: Literal["stub", "real"] = Field(
        default="stub",
        description="Flips all LLM/embedding adapters between stub and real providers.",
    )

    # Which real LLM provider drives generation (D-09). Ignored in stub mode.
    # The judge always uses the complement provider (D-04, cross-family bias avoidance).
    llm_real_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic",
        description=(
            "When llm_provider='real', selects which provider drives generation. "
            "The judge uses the complement provider (D-04). Ignored in stub mode."
        ),
    )

    # Optional secrets — never logged, never serialized into /health.
    anthropic_api_key: SecretStr | None = Field(default=None)
    openai_api_key: SecretStr | None = Field(default=None)

    # OpenAI-compatible endpoint override (D-14). Set DOCINTEL_OPENAI_BASE_URL to
    # point the OpenAI adapter at any chat-completions-compatible gateway — e.g.
    # NVIDIA NIM hosted catalog ("https://integrate.api.nvidia.com/v1") serving
    # open-weight models like openai/gpt-oss-120b. None → the SDK default
    # (api.openai.com). The nvapi-... key goes in openai_api_key.
    openai_base_url: str | None = Field(default=None)

    # Generator model for the OpenAI adapter. Default gpt-4o (the v1.0 baseline).
    # Override to a NIM catalog id (e.g. "openai/gpt-oss-120b") via
    # DOCINTEL_OPENAI_MODEL. Must be keyed in pricing.py or cost_for() raises (D-06).
    openai_model: str = Field(default="gpt-4o")

    # Cross-family judge model (D-14). When set AND llm_real_provider='openai',
    # the judge is a SECOND OpenAIAdapter pinned to this model rather than the
    # Anthropic complement — enabling distinct-model cross-family judging against
    # a single OpenAI-compatible gateway (e.g. generator=openai/gpt-oss-120b,
    # judge=meta/llama-3.3-70b-instruct, both via NIM). None preserves the v1.0
    # cross-PROVIDER behaviour (D-04). See ADR-014.
    judge_model: str | None = Field(default=None)

    # EMP-01: optional SEPARATE API key for the judge adapter. NIM free-tier caps
    # total requests per worker (~32); a 32-question eval makes 64 calls (gen+judge)
    # and exhausts one key. Putting the judge on a SECOND nvapi key gives it an
    # independent worker budget so the full frozen benchmark runs on free NIM.
    # None → judge reuses openai_api_key (single-key behaviour, unchanged).
    judge_openai_api_key: SecretStr | None = Field(default=None)

    # Where ingestion artifacts land (Phase 3+ will use this).
    data_dir: str = Field(default="data")

    # Injected by Docker build (ARG GIT_SHA → ENV DOCINTEL_GIT_SHA). Defaults to "unknown" locally.
    git_sha: str = Field(default="unknown")

    # URL the UI uses to reach the API. Default targets compose's `api` service.
    # Consumed by docintel-ui (Plan 04). Lives here so config.py remains the only env reader (D-18).
    api_url: str = Field(default="http://api:8000")

    # Phase 3 amendment (D-19). SEC fair-access policy requires a
    # descriptive User-Agent on every request. Format: "Name email@example.com".
    # Required in real-fetch mode; stub-mode CI never hits sec.gov so a default
    # placeholder is safe at the Settings level — validation lives at the
    # fetch.py call site (raise if blank when network mode is on).
    edgar_user_agent: str = Field(
        default="docintel-ci ci@example.com",
        description=(
            "Identifying User-Agent for SEC EDGAR requests. Format: "
            "'YourName your.email@example.com'. SEC blocks requests without "
            "a valid identifying UA. Default is a CI placeholder; developer "
            "machines MUST override via DOCINTEL_EDGAR_USER_AGENT."
        ),
    )
    edgar_request_rate_hz: float = Field(
        default=8.0,
        description=(
            "Soft request rate for SEC fetcher (sec-edgar-downloader enforces "
            "10 req/sec internally via pyrate-limiter; this is a defensive "
            "headroom value, not a second throttle)."
        ),
    )

    # Phase 4 amendment (D-17). Index location + Qdrant connection metadata.
    # Single env-reader rule (FND-11) means these live here, not in
    # docintel_index. The two qdrant-* fields default to the docker-compose
    # service-name target and are consulted ONLY when llm_provider == "real"
    # (D-03 lazy-import discipline — stub-mode CI never reads them).
    index_dir: str = Field(
        default="data/indices",
        description=(
            "Where index artifacts land " "(data/indices/dense/, /bm25/, /MANIFEST.json)."
        ),
    )
    # Phase 12 amendment (D-03). Consolidated JSONL trace sink location.
    # Mirrors index_dir; single env-reader rule (FND-11) means it lives here.
    trace_dir: str = Field(
        default="data/traces",
        description=(
            "Where consolidated trace_completed JSONL records land "
            "(data/traces/<run>.jsonl). Gitignored, mirrors index_dir."
        ),
    )
    qdrant_url: str = Field(
        default="http://qdrant:6333",
        description=(
            "Qdrant HTTP endpoint. Default targets the docker-compose service "
            "name. Consulted ONLY when llm_provider == 'real' (D-03 factory "
            "lazy-import discipline). Stub mode never reads this field."
        ),
    )
    qdrant_collection: str = Field(
        default="docintel-dense-v1",
        description="Qdrant collection name for the dense index (D-06).",
    )
