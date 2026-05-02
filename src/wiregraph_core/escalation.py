"""Suspicious → prohibited escalation counters (framework-agnostic).

Counts hits on a ``(tenant, asset, sink)``-style key inside a sliding window
backed by an injected :class:`CacheProtocol`. Returns ``True`` when the next
alert should be promoted; the counter is reset on promotion so the next page
requires a full new window's worth of hits.

ORM rollups for "how often did promotions actually fire" stay in the host
wrapper — this module only owns the cache arithmetic.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from wiregraph_core.cache import CacheProtocol

_PREFIX = "wiregraph:esc:"


def _key(parts: Iterable[object]) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}{digest}"


def should_escalate(
    cache: CacheProtocol,
    parts: Iterable[object],
    threshold: int,
    window_seconds: int,
) -> bool:
    """Return True when the *next* hit for ``parts`` should be promoted.

    On True, the counter is reset; the caller must accumulate another full
    window before being notified again. ``threshold <= 0`` disables.
    """
    if threshold <= 0:
        return False
    key = _key(parts)
    if cache.add(key, 1, timeout=window_seconds):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window_seconds)
            count = 1
    if count >= threshold:
        cache.delete(key)
        return True
    return False
