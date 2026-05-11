"""Cache contract for core modules that need short-lived counters.

Escalation and dedup take an injected :class:`CacheProtocol` rather than
reaching for ``django.core.cache`` directly. The Django-backed adapter lives
in ``wiregraph_apps.detection.adapters.cache``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheProtocol(Protocol):
    """Minimal cache surface used by escalation counters and dedup.

    Semantics mirror ``django.core.cache.cache``: ``get`` returns ``default``
    on miss, ``set`` overwrites, ``incr`` raises ``ValueError`` if the key is
    missing (callers must seed with ``set`` first or use ``get_or_set``).
    ``add`` is atomic: it stores the value only if the key is absent and
    returns True in that case, False otherwise — dedup relies on this to
    deliver exactly one alert per window without a race.
    """

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any, timeout: int | None = None) -> None: ...

    def add(self, key: str, value: Any, timeout: int | None = None) -> bool: ...

    def incr(self, key: str, delta: int = 1) -> int: ...

    def delete(self, key: str) -> None: ...
