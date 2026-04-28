"""FastAPI application for docintel.

Phase 1 scope: introspective GET /health only. Phase 13 will add POST /query and
GET /trace/{id} (API-01 in REQUIREMENTS.md). Phase 2 will extend /health with
adapter introspection — do NOT add it here.

Per CONTEXT.md D-18, this module MUST NOT read environment variables directly.
All configuration flows through docintel_core.config.Settings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging
from fastapi import FastAPI
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration / app construction
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _settings() -> Settings:
    """Memoized Settings — Settings() reads env exactly once per process."""
    return Settings()


def reset_settings_cache() -> None:
    """Public hook for tests; clears the lru_cache on _settings().

    Tests must NOT import the underscore-prefixed `_settings` directly. They
    call this function to force a re-read of the environment between cases.
    """
    _settings.cache_clear()


configure_logging()

app = FastAPI(
    title="docintel API",
    version=__version__,
    description=(
        "Production-shaped RAG over SEC 10-K filings. " "Phase 1: scaffold + /health only."
    ),
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Locked /health JSON shape — see CONTEXT.md D-15.

    Phase 2 may extend this model (e.g. adapters block); existing fields MUST
    NOT change shape or rename.
    """

    status: Literal["ok"]
    service: Literal["docintel-api"]
    version: str
    provider: Literal["stub", "real"]
    git_sha: str
    timestamp: str  # ISO-8601 UTC


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    settings = _settings()
    return HealthResponse(
        status="ok",
        service="docintel-api",
        version=__version__,
        provider=settings.llm_provider,
        git_sha=settings.git_sha,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )


# ---------------------------------------------------------------------------
# Console-script entrypoint (referenced by packages/docintel-api/pyproject.toml)
# ---------------------------------------------------------------------------


def run() -> None:
    """Launch uvicorn against this app. Used by the `docintel-api` console script."""
    import uvicorn

    uvicorn.run(
        "docintel_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None,  # let structlog/stdlib handle formatting
    )


if __name__ == "__main__":
    run()
