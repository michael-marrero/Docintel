"""Structural test: only ``docintel_core.config`` may read environment vars.

CONTEXT.md D-18 mandates a single env-reader. This test scans every Python
file under ``packages/*/src`` and fails if any module other than
``packages/docintel-core/src/docintel_core/config.py`` contains the strings
``os.environ`` or ``os.getenv``.

The test is grep-style on purpose: AST analysis would miss dynamic access
patterns and conditional imports that still ultimately read env. We accept
false positives (e.g. the strings appearing in a docstring) — the cost of a
trivial workaround is far smaller than the cost of letting a real escape
slip through CI.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# Repo root is two levels up from this file: tests/<file>.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
_ALLOWED_FILE = (
    _PACKAGES / "docintel-core" / "src" / "docintel_core" / "config.py"
).resolve()

_FORBIDDEN_TOKENS = ("os.environ", "os.getenv")


def _iter_source_files() -> list[Path]:
    if not _PACKAGES.exists():
        pytest.skip("packages/ directory not present in this checkout")
    return [p.resolve() for p in _PACKAGES.glob("*/src/**/*.py")]


def test_only_config_reads_env() -> None:
    offenders: list[tuple[Path, str]] = []
    for path in _iter_source_files():
        if path == _ALLOWED_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_TOKENS:
            if token in text:
                offenders.append((path, token))

    assert not offenders, (
        "Direct env reads found outside docintel_core.config:\n"
        + "\n".join(f"  - {p.relative_to(_REPO_ROOT)}: {tok}" for p, tok in offenders)
    )


def test_allowed_file_exists() -> None:
    """Sanity: the one allow-listed file must actually be present.

    Otherwise a future refactor could rename ``config.py`` and silently
    bypass this guard (every file would be 'not the allow-listed file').
    """
    assert _ALLOWED_FILE.is_file(), f"missing allow-listed config file: {_ALLOWED_FILE}"
