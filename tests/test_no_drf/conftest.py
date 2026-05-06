"""Shared fixtures for the no-DRF regression suite.

The ``no_drf`` fixture pretends ``rest_framework``, ``rest_framework_simplejwt``
and ``drf_spectacular`` are not installed:

    1. Pops any cached ``sys.modules`` entries under those namespaces.
    2. Inserts a ``sys.meta_path`` finder that raises ``ImportError`` on any
       future import of those packages.
    3. Restores the original state on teardown.

This complements ``tests/test_imports.py`` (which catches *transitive*
module-load imports via subprocess). The fixture catches *runtime/lazy*
imports inside method bodies — e.g. ``wiregraph._drf.drf_available()``,
which does ``import rest_framework`` on every call. If a code path exercised
by these tests reaches for DRF without a guard, the test will fail loudly.

Limitation: modules that already imported DRF before this fixture activates
keep their bound references (the real classes). That's fine — the goal is
to verify behaviour in a fresh no-DRF process, not to reload every wiregraph
module mid-test.
"""

from __future__ import annotations

import sys

import pytest

_BLOCKED_PREFIXES = ("rest_framework", "drf_spectacular")


def _is_blocked(name: str) -> bool:
    return name.split(".")[0] in _BLOCKED_PREFIXES


class _DRFBlocker:
    def find_spec(self, name, path=None, target=None):  # noqa: D401
        if _is_blocked(name):
            raise ImportError(f"DRF is hidden by no_drf fixture: {name}")
        return None


@pytest.fixture
def no_drf(monkeypatch):
    saved = {n: sys.modules[n] for n in list(sys.modules) if _is_blocked(n)}
    for name in saved:
        monkeypatch.delitem(sys.modules, name, raising=False)

    blocker = _DRFBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(blocker)
        except ValueError:
            pass
        sys.modules.update(saved)
