"""Plan 06-01 Wave 0 xfail scaffolds for D-03 make_generator factory + lazy-import gate.

Covers VALIDATION.md row 06-04-* (D-03) — the fourth sibling factory
alongside ``make_adapters`` / ``make_index_stores`` / ``make_retriever``:

* test_make_generator_stub — ``make_generator(Settings(llm_provider="stub"))``
  returns a ``Generator`` instance (D-03 dispatch + composition: internally
  calls ``make_adapters(cfg)`` for the bundle and ``make_retriever(cfg)``
  for the retriever, then constructs ``Generator(bundle, retriever)``).
* test_factory_lazy_imports_generator_module — D-12 + Pattern S5: importing
  ``docintel_core.adapters.factory`` does NOT eagerly load
  ``docintel_generate.generator``; the import lives INSIDE the
  ``make_generator`` function body so module-load cost stays cheap for
  callers that only need ``make_adapters`` (e.g., Phase 4 index build).

Both tests are xfail-strict-marked because ``make_generator`` does not
yet exist in ``docintel_core.adapters.factory`` at Wave 0. The
in-function ``from docintel_core.adapters.factory import make_generator``
raises ImportError → pytest counts this as the expected failure under
xfail(strict=True). Plan 06-04 ships ``make_generator`` + the
``Generator`` class and these xfails flip to passing.

Analogs:
* ``tests/test_make_retriever.py`` (full file, lines 1-110) — Phase 5
  D-04 third-sibling factory analog; same lazy-import-gate hermetic-reset
  pattern at lines 67-100.
* ``tests/test_adapters.py:test_stub_no_sdk_import`` (lines 165-187) — the
  D-12 lazy-import gate test pattern.
* 06-PATTERNS.md §"Tests scaffolds" line 850 (analog assignment).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 ships make_generator + Generator")
def test_make_generator_stub() -> None:
    """D-03 — make_generator(Settings(llm_provider='stub')) returns a Generator.

    Phase 5 D-04 third-sibling-factory precedent: the factory constructs
    a stub-mode bundle, a stub-mode retriever, and composes them into a
    ``Generator``. We assert the class name + module to avoid coupling the
    test to the import of ``Generator`` (which would itself fail-and-xfail
    on Wave 0; isolating to the factory's return type makes the test
    progress through Wave 2 specifically rather than being entangled with
    Wave 1's ``prompts.py`` ImportError).
    """
    from docintel_core.adapters.factory import make_generator
    from docintel_core.config import Settings

    g = make_generator(Settings(llm_provider="stub"))
    assert g.__class__.__name__ == "Generator", (
        f"D-03: make_generator must return a Generator; got {g.__class__.__name__!r}"
    )
    assert g.__class__.__module__ == "docintel_generate.generator", (
        f"D-03: Generator must live in docintel_generate.generator; "
        f"got module={g.__class__.__module__!r}"
    )


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 06-04 wires make_generator lazy-import")
def test_factory_lazy_imports_generator_module() -> None:
    """D-12 + Pattern S5 — importing the factory does NOT load docintel_generate.

    The ``from docintel_generate.generator import Generator`` statement
    inside ``make_generator`` must live in the function body, NOT at
    module top, so ``import docintel_core.adapters.factory`` stays cheap
    for callers (e.g., Phase 4 index build) that never call
    ``make_generator``.

    Hermetic-reset pattern (matches ``tests/test_make_retriever.py:67-100``):
    drop any cached ``docintel_generate*`` modules + the factory module
    BEFORE the import so a prior test that pulled in ``docintel_generate``
    does not contaminate this assertion.
    """
    import sys

    # Drop any cached docintel_generate modules so the test is hermetic.
    for mod in list(sys.modules):
        if mod.startswith("docintel_generate"):
            del sys.modules[mod]
    # Also drop the factory so its module-load runs again.
    sys.modules.pop("docintel_core.adapters.factory", None)

    # Importing the factory must NOT pull in docintel_generate.
    from docintel_core.adapters import factory

    # First — assert make_generator is exposed on the factory module. Under Wave 0
    # this fails with AttributeError (the function does not exist yet) so the
    # whole test fails → xfail(strict=True) holds. Plan 06-04 lands the
    # function and the assertion flips to true.
    assert hasattr(factory, "make_generator"), (
        "D-03: docintel_core.adapters.factory must expose make_generator "
        "(Wave 2 — Plan 06-04 lands the 4th sibling factory)."
    )
    # Second — the lazy-import gate proper. Importing factory must NOT
    # eagerly load docintel_generate.generator (Pattern S5; D-12).
    assert "docintel_generate.generator" not in sys.modules, (
        "D-12 + Pattern S5: factory module top-level pulled in "
        "docintel_generate.generator eagerly; the import must live inside "
        "make_generator()."
    )
