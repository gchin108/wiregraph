"""Alert dedup / rate-limit helper (framework-agnostic).

The host injects a :class:`CacheProtocol`. ``cache.add`` must be atomic and
succeed only when the key is absent, so "always deliver the first occurrence"
falls out for free — the first call in a window returns True, subsequent
calls within the TTL return False.

Multi-process deployments must use a cross-process cache backend (Redis,
Memcached, database). A per-process backend will let each worker alert
independently.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from wiregraph_core.cache import CacheProtocol

_PREFIX = "wiregraph:dedup:"


def _key(parts: Iterable[object]) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}{digest}"


def should_emit(
    cache: CacheProtocol, parts: Iterable[object], window_seconds: int
) -> bool:
    """Return True if an alert for ``parts`` should be emitted right now.

    Returns True on the first call within ``window_seconds``; False for any
    repeat within the window. A zero/negative window disables dedup.
    """
    if window_seconds <= 0:
        return True
    return bool(cache.add(_key(parts), 1, timeout=window_seconds))
