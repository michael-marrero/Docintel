"""Story 2.1 — the FastAPI app serves the static frontend without shadowing the
API routes. AD-15: the UI is delivered over HTTP from the same origin as the API.
"""

from docintel_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_root_serves_index_html_with_command_bar():
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    # the command bar is the front door — its prompt + input must be present
    assert 'id="command-bar"' in res.text
    assert 'id="command-input"' in res.text


def test_static_assets_served_with_correct_types():
    js = client.get("/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]

    css = client.get("/tokens.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]

    lib = client.get("/lib.js")
    assert lib.status_code == 200
    assert "parseCommand" in lib.text  # the real module, not a 404 page


def test_api_routes_not_shadowed_by_static_mount():
    # The "/" StaticFiles mount must not swallow the JSON API routes.
    assert client.get("/health").status_code == 200
    cov = client.get("/coverage")
    assert cov.status_code == 200
    assert "corpus" in cov.json()


def test_unknown_path_404s_without_index_fallback():
    res = client.get("/does-not-exist.js")
    assert res.status_code == 404
    # html=True must NOT SPA-fallback unknown paths to index.html — a broken
    # mount that served index for everything would otherwise pass a bare 404 check.
    assert 'id="command-bar"' not in res.text


def test_frontend_uses_tokens_not_hardcoded_hex():
    # app.css must consume the design tokens (Story 2.0), not hard-code hex —
    # otherwise the token single-source-of-truth (UX-DR1) is already broken.
    css = client.get("/app.css").text
    assert "var(--" in css
    # no hex color literals at all — 3/4/6/8-digit (the {6}-only guard missed
    # #fff shorthand and #rrggbbaa). The token file is the single source of truth.
    import re

    assert not re.search(r"#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])", css)
