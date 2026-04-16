"""Tenant resolution for incoming requests.

A request is associated with exactly one tenant via the first active
``TenantMembership`` for the authenticated user. Anonymous users and users
without any membership resolve to ``None`` — callers must treat that as a
signal to skip tenant-scoped work rather than attaching to a shared fallback.

A ``ContextVar`` mirrors the per-request tenant so that code outside the
request/response cycle (e.g. the egress interceptor running inside application
code that calls ``requests``) can discover the active tenant without needing
an ``HttpRequest``.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

    from core_apps.tenants.models import Tenant


_CACHE_ATTR = "_wiregraph_tenant"
_SENTINEL = object()

_current_tenant: ContextVar["Tenant | None"] = ContextVar(
    "wiregraph_current_tenant", default=None
)


def resolve_tenant(request: "HttpRequest") -> "Tenant | None":
    cached = getattr(request, _CACHE_ATTR, _SENTINEL)
    if cached is not _SENTINEL:
        return cached

    tenant = _lookup_tenant(request)
    setattr(request, _CACHE_ATTR, tenant)
    return tenant


def _lookup_tenant(request: "HttpRequest") -> "Tenant | None":
    from wiregraph.resolvers import load_configured

    return load_configured()(request)


def get_current_tenant() -> "Tenant | None":
    return _current_tenant.get()


def set_current_tenant(tenant: "Tenant | None"):
    return _current_tenant.set(tenant)


def reset_current_tenant(token) -> None:
    _current_tenant.reset(token)
