"""Story 2.0 — design token foundation.

The load-bearing invariant is accessibility (UX-DR1/DR2), not "the file parses".
This asserts the AA-critical contrast pairs DESIGN.md documents actually hold on
both surfaces, that the token set is complete, and that no drop-shadow token
exists (UX-DR3). Pure stdlib — no deps.
"""

import re
from pathlib import Path

TOKENS = Path(__file__).resolve().parents[1] / "web" / "tokens.css"


# ---- parse tokens.css into per-selector var maps -------------------------------


def _blocks(css: str) -> list[tuple[str, dict[str, str]]]:
    """Return (selector, {var: value}) for each rule block, in source order."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # comments carry colons — strip first
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip().splitlines()[-1].strip()
        decls = {}
        for d in m.group(2).split(";"):
            if ":" not in d:
                continue
            name, _, val = d.partition(":")
            name, val = name.strip(), val.strip()
            if name.startswith("--"):
                decls[name] = val
        out.append((selector, decls))
    return out


def _resolve(surface: dict[str, str]) -> dict[str, str]:
    """Resolve one level of var(--x) references within a surface."""
    resolved = dict(surface)
    for k, v in surface.items():
        ref = re.fullmatch(r"var\((--[\w-]+)\)", v)
        if ref:
            resolved[k] = surface.get(ref.group(1), v)
    return resolved


def _surfaces() -> tuple[dict[str, str], dict[str, str]]:
    css = TOKENS.read_text()
    blocks = _blocks(css)
    dark: dict[str, str] = {}
    light: dict[str, str] = {}
    for selector, decls in blocks:
        if selector == ":root":
            dark.update(decls)  # multiple :root blocks accumulate onto dark
        elif '[data-theme="light"]' in selector:
            light.update(decls)
    # light re-declares only color; inherits type/shape/spacing from :root
    effective_light = {**dark, **light}
    return _resolve(dark), _resolve(effective_light)


# ---- WCAG 2.x contrast ---------------------------------------------------------


def _rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.strip().lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def _lum(hex_str: str) -> float:
    r, g, b = _rgb(hex_str)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---- tests ---------------------------------------------------------------------

DARK, LIGHT = _surfaces()

AA_TEXT = 4.5  # WCAG 2.2 AA normal text
AA_UI = 3.0  # WCAG 2.2 AA UI components / large text


def _c(surface, fg, bg):
    return contrast(surface[fg], surface[bg])


def test_dark_text_ink_pairs_pass_aa():
    for bg in ("--card", "--canvas", "--card-recessed"):
        assert _c(DARK, "--ink-faint", bg) >= AA_TEXT, bg  # locators (doc 4.67/4.98/4.79)
        assert _c(DARK, "--ink", bg) >= AA_TEXT, bg  # primary ink
        assert _c(DARK, "--prose", bg) >= AA_TEXT, bg  # body prose


def test_dark_ui_pairs_pass_aa():
    assert _c(DARK, "--accent-dim", "--hairline") >= AA_UI  # CI band vs track (doc 3.5)
    assert _c(DARK, "--alert", "--card") >= AA_UI  # error rail (doc 6.1)
    assert _c(DARK, "--accent", "--card") >= AA_UI  # teal number/fill


def test_light_text_ink_pairs_pass_aa():
    for bg in ("--card", "--canvas", "--card-recessed"):
        assert _c(LIGHT, "--ink-faint", bg) >= AA_TEXT, bg  # locators (doc 5.04/4.86/4.61)
        assert _c(LIGHT, "--ink", bg) >= AA_TEXT, bg
        assert _c(LIGHT, "--prose", bg) >= AA_TEXT, bg


def test_light_teal_split_passes_aa():
    # UX-DR2: accent-text-light is AA as TEXT; accent-light is only ≥3:1 as fill.
    for bg in ("--card", "--canvas", "--card-recessed"):
        assert _c(LIGHT, "--accent-text-light", bg) >= AA_TEXT, bg  # doc 5.47/5.29/5.01
    assert _c(LIGHT, "--accent-light", "--hairline") >= AA_UI  # bar fill vs track (doc 3.01)
    assert _c(LIGHT, "--alert", "--card") >= AA_UI  # doc 4.36


def test_token_set_is_complete_on_both_surfaces():
    dark_colors = {
        "--canvas",
        "--card",
        "--card-recessed",
        "--ink",
        "--ink-dim",
        "--ink-faint",
        "--prose",
        "--hairline",
        "--accent",
        "--accent-dim",
        "--accent-wash",
        "--accent-mark",
        "--alert",
    }
    assert dark_colors <= DARK.keys()
    light_colors = dark_colors | {"--accent-light", "--accent-text-light"}
    assert light_colors <= LIGHT.keys()
    # two type families, 3 radii, 4px spacing unit
    assert {"--font-sans", "--font-mono"} <= DARK.keys()
    assert {"--radius-sm", "--radius", "--radius-frame"} <= DARK.keys()
    assert DARK["--space-unit"] == "4px"


def test_no_drop_shadows_anywhere():
    # UX-DR3: depth is tonal only. Absence of shadow tokens is the enforcement.
    css = TOKENS.read_text().lower()
    assert "box-shadow" not in css
    assert "--shadow" not in css


def test_light_is_co_equal_not_invert():
    # A real re-declaration, not default-plus-invert: light must set its own
    # surface + ink hexes, and they must differ from dark.
    for k in ("--canvas", "--card", "--ink", "--hairline"):
        assert DARK[k].lower() != LIGHT[k].lower(), k


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all design-token checks passed")
