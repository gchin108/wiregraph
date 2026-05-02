import pytest

from wiregraph_core.scanner.presidio import (
    PresidioScanner,
    PresidioUnavailable,
    dedupe_against,
)
from wiregraph_core.types import Match


def test_dedupe_drops_overlapping_same_asset_match():
    regex = [Match("email", 0, 16, "a@b.co", 0.99)]
    presidio = [
        Match("email", 5, 12, "x", 0.85),
        Match("person_name", 20, 30, "Jane Doe", 0.8),
    ]
    kept = dedupe_against(presidio, regex)
    assert [m.asset_name for m in kept] == ["person_name"]


def test_dedupe_keeps_different_asset_on_same_span():
    regex = [Match("email", 0, 20, "x", 0.99)]
    presidio = [Match("person_name", 5, 15, "x", 0.8)]
    assert dedupe_against(presidio, regex) == presidio


def test_presidio_missing_raises_presidio_unavailable(monkeypatch):
    import wiregraph_core.scanner.presidio as mod

    def fake_import():
        raise PresidioUnavailable("simulated missing presidio")

    monkeypatch.setattr(mod, "_import_analyzer", fake_import)
    scanner = PresidioScanner()
    with pytest.raises(PresidioUnavailable):
        scanner.scan("some text with jane@example.com")


_has_presidio = True
try:
    import presidio_analyzer  # noqa: F401
except ImportError:
    _has_presidio = False

requires_presidio = pytest.mark.skipif(
    not _has_presidio, reason="presidio extra not installed"
)


@requires_presidio
def test_presidio_detects_person_name():
    scanner = PresidioScanner(min_score=0.5)
    matches = scanner.scan("Jane Doe lives in Paris and her card is 4111111111111111.")
    names = {m.asset_name for m in matches}
    assert "person_name" in names or "address" in names


@requires_presidio
def test_presidio_empty_input():
    assert PresidioScanner().scan("") == []
