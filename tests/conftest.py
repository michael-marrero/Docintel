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

    Phase 13 (Plan 13-02): the chdir-to-tmp_path also moves the ``data_dir``
    / ``index_dir`` defaults (``"data"`` / ``"data/indices"``) off the project
    root, so anything that exercises ``make_generator(_settings())`` (the new
    POST /query handler) would fail with a missing MANIFEST. Re-point the four
    data env vars at the PROJECT ROOT's real paths via absolute paths, BEFORE
    the chdir. Tests that need different paths (e.g. test_api_traces.py
    re-pointing trace_dir at a seeded tmp dir) can still override via
    ``monkeypatch.setenv(...)`` after this fixture runs — monkeypatch
    re-sets, not appends. The /health + trace_middleware tests don't touch
    data dirs at all, so the absolute paths are harmless there.
    """
    import os
    from pathlib import Path

    for key in list(os.environ):
        if key.startswith("DOCINTEL_") or key == "LLM_PROVIDER":
            monkeypatch.delenv(key, raising=False)

    # Resolve the project root: this file is tests/conftest.py, so root is
    # the parent of "tests". Use absolute paths so the post-chdir Settings()
    # reads them verbatim, independent of cwd.
    project_root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("DOCINTEL_DATA_DIR", str(project_root / "data"))
    monkeypatch.setenv("DOCINTEL_INDEX_DIR", str(project_root / "data" / "indices"))
    monkeypatch.setenv("DOCINTEL_TRACE_DIR", str(project_root / "data" / "traces"))

    monkeypatch.chdir(tmp_path)


@pytest.fixture
def client(clean_docintel_env) -> Iterator[TestClient]:
    """FastAPI TestClient with a freshly-cleared Settings + Generator cache.

    We import lazily so ``clean_docintel_env`` (and thus ``monkeypatch.chdir``)
    runs before the app module is touched. ``reset_settings_cache`` and
    ``reset_generator_cache`` are the public hooks documented in
    ``docintel_api.main`` for exactly this purpose — clearing both prevents a
    prior test's cached Generator (built against a different Settings) from
    leaking into the next case.
    """
    from docintel_api.main import app, reset_generator_cache, reset_settings_cache

    reset_settings_cache()
    reset_generator_cache()
    with TestClient(app) as c:
        yield c
    reset_settings_cache()
    reset_generator_cache()


@pytest.fixture
def stub_bundle(clean_docintel_env):
    """AdapterBundle constructed in stub mode with a sanitised environment.

    Lazy-imports docintel_core.adapters so that pytest collection succeeds
    even before Wave 1 lands the adapter package. Tests that consume this
    fixture should themselves be xfail-marked until Wave 1+ ships the code.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings

    return make_adapters(Settings(llm_provider="stub"))
