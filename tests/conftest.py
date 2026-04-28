"""Shared pytest fixtures for the docintel test suite.

Two responsibilities:

1. ``clean_docintel_env`` — strip any DOCINTEL_* / LLM_PROVIDER environment
   variables that may have been set by the developer's shell or a prior test,
   and ``chdir`` into a fresh ``tmp_path`` so the repo-root ``.env`` file is
   not picked up by pydantic-settings. Without the chdir, ``Settings()`` would
   read ``.env`` and the "default is stub" guarantee would silently depend on
   the contents of that file.

2. ``client`` — a FastAPI ``TestClient`` for the docintel-api app. We import
   the *public* ``reset_settings_cache`` hook (NOT the private ``_settings``
   lru_cache) so the cache is cleared between tests after the env has been
   sanitised by ``clean_docintel_env``.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def clean_docintel_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Isolate a test from the developer's environment and the repo .env.

    Removes any envvar that pydantic-settings would feed into ``Settings``
    (DOCINTEL_* prefix plus the bare ``LLM_PROVIDER`` legacy name) and
    relocates the working directory so a stray repo-root ``.env`` cannot
    leak into the test.
    """
    import os

    for key in list(os.environ):
        if key.startswith("DOCINTEL_") or key == "LLM_PROVIDER":
            monkeypatch.delenv(key, raising=False)

    monkeypatch.chdir(tmp_path)


@pytest.fixture
def client(clean_docintel_env) -> Iterator[TestClient]:
    """FastAPI TestClient with a freshly-cleared Settings cache.

    We import lazily so ``clean_docintel_env`` (and thus ``monkeypatch.chdir``)
    runs before the app module is touched. ``reset_settings_cache`` is the
    public hook documented in ``docintel_api.main`` for exactly this purpose.
    """
    from docintel_api.main import app, reset_settings_cache

    reset_settings_cache()
    with TestClient(app) as c:
        yield c
    reset_settings_cache()
