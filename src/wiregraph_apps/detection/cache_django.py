"""Django adapter exposing :data:`django.core.cache.cache` as a CacheProtocol.

The default Django cache instance already satisfies
:class:`wiregraph_core.cache.CacheProtocol` (``get``/``set``/``add``/``incr``/
``delete`` with the documented semantics). This module gives the wrappers a
single, named import to inject so swapping the backend later is one edit.
"""

from __future__ import annotations

from django.core.cache import cache as _django_cache

from wiregraph_core.cache import CacheProtocol


def get_cache() -> CacheProtocol:
    return _django_cache
