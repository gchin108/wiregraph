"""Django adapter for :mod:`wiregraph_core.scanner.regex`.

Reads ``WIREGRAPH`` settings to build a :class:`DetectionConfig`, wraps
``CustomPatternError`` in :class:`ImproperlyConfigured`, and re-exports the
public names existing call sites import.
"""

from __future__ import annotations

from typing import Iterable

from django.core.exceptions import ImproperlyConfigured

from wiregraph_apps.common.conf import (
    get_custom_patterns,
    get_redact_strategy,
)
from wiregraph_core.scanner.regex import (
    CustomPatternError,
    RegexScanner as _CoreRegexScanner,
    _compile_custom_patterns as _core_compile_custom_patterns,
    _luhn_valid,  # noqa: F401 — used by tests
    redact as _core_redact,
    redact_matches as _core_redact_matches,
)
from wiregraph_core.types import Match


__all__ = [
    "Match",
    "RegexScanner",
    "redact",
    "redact_matches",
    "_compile_custom_patterns",
    "_luhn_valid",
]


class RegexScanner(_CoreRegexScanner):
    """No-arg-friendly wrapper that defaults custom patterns from settings."""

    def __init__(self, custom_patterns: list[dict] | None = None):
        specs = custom_patterns if custom_patterns is not None else get_custom_patterns()
        try:
            super().__init__(custom_patterns=specs)
        except CustomPatternError as e:
            raise ImproperlyConfigured(str(e)) from e


def _compile_custom_patterns(specs: list[dict]):
    try:
        return _core_compile_custom_patterns(specs)
    except CustomPatternError as e:
        raise ImproperlyConfigured(str(e)) from e


def redact(value: str, strategy: str | None = None) -> str:
    return _core_redact(value, strategy or get_redact_strategy())


def redact_matches(matches: Iterable[Match], strategy: str | None = None) -> list[str]:
    return _core_redact_matches(matches, strategy or get_redact_strategy())
