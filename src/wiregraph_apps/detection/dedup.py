"""Django adapter for :mod:`wiregraph_core.dedup`.

Injects ``django.core.cache.cache`` into the pure helper so existing call
sites can keep using ``should_emit(parts, window_seconds)`` unchanged.
"""

from __future__ import annotations

from typing import Iterable

from django.core.cache import cache

from wiregraph_core.dedup import should_emit as _should_emit


def should_emit(parts: Iterable[object], window_seconds: int) -> bool:
    return _should_emit(cache, parts, window_seconds)
