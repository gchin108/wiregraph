"""WireGraph — runtime PII detection for Django.

Public API:

    wiregraph.setup(MIDDLEWARE) -> list[str]   # one-call middleware installer
    wiregraph.JWTAuthMiddleware                # re-export (lazy)
    wiregraph.PIIDetectionMiddleware           # re-export (lazy)
    wiregraph.resolvers                        # pluggable tenant resolvers
    wiregraph.WiregraphSettings                # TypedDict for IDE completion

Middleware classes are resolved lazily via ``__getattr__`` so that importing
this package from a Django settings file does not trigger Django app loading.
"""

from __future__ import annotations

from wiregraph.apps import INSTALLED_APPS
from wiregraph.setup import setup

__all__ = [
    "setup",
    "resolvers",
    "INSTALLED_APPS",
    "JWTAuthMiddleware",
    "PIIDetectionMiddleware",
    "WiregraphSettings",
]


def __getattr__(name: str):
    if name == "JWTAuthMiddleware":
        from core_apps.common.middleware import JWTAuthMiddleware

        return JWTAuthMiddleware
    if name == "PIIDetectionMiddleware":
        from core_apps.detection.middleware import PIIDetectionMiddleware

        return PIIDetectionMiddleware
    if name == "WiregraphSettings":
        from core_apps.common.conf import WiregraphSettings

        return WiregraphSettings
    if name == "resolvers":
        import importlib

        return importlib.import_module("wiregraph.resolvers")
    raise AttributeError(f"module 'wiregraph' has no attribute {name!r}")
