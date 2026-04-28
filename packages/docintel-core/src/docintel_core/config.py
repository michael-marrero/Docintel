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

    # Optional secrets — never logged, never serialized into /health.
    anthropic_api_key: SecretStr | None = Field(default=None)
    openai_api_key: SecretStr | None = Field(default=None)

    # Where ingestion artifacts land (Phase 3+ will use this).
    data_dir: str = Field(default="data")

    # Injected by Docker build (ARG GIT_SHA → ENV DOCINTEL_GIT_SHA). Defaults to "unknown" locally.
    git_sha: str = Field(default="unknown")

    # URL the UI uses to reach the API. Default targets compose's `api` service.
    # Consumed by docintel-ui (Plan 04). Lives here so config.py remains the only env reader (D-18).
    api_url: str = Field(default="http://api:8000")
