"""Cache contract for core modules that need short-lived counters.

Phase 2 will replace direct ``django.core.cache`` calls in escalation/dedup
with an injected implementation of :class:`CacheProtocol`. A Django-backed
adapter will live in ``wiregraph_apps.detection.cache_django``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheProtocol(Protocol):
    """Minimal cache surface used by escalation counters and dedup.

    Semantics mirror ``django.core.cache.cache``: ``get`` returns ``default``
    on miss, ``set`` overwrites, ``incr`` raises ``ValueError`` if the key is
    missing (callers must seed with ``set`` first or use ``get_or_set``).
    """

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any, timeout: int | None = None) -> None: ...

    def incr(self, key: str, delta: int = 1) -> int: ...

    def delete(self, key: str) -> None: ...
