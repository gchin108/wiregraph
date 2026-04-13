"""Tenant resolution for incoming requests.

A request is associated with exactly one tenant via the first active
``TenantMembership`` for the authenticated user. Anonymous users and users
without any membership resolve to ``None`` — callers must treat that as a
signal to skip tenant-scoped work rather than attaching to a shared fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

    from core_apps.tenants.models import Tenant


_CACHE_ATTR = "_wiregraph_tenant"
_SENTINEL = object()


def resolve_tenant(request: "HttpRequest") -> "Tenant | None":
    cached = getattr(request, _CACHE_ATTR, _SENTINEL)
    if cached is not _SENTINEL:
        return cached

    tenant = _lookup_tenant(request)
    setattr(request, _CACHE_ATTR, tenant)
    return tenant


def _lookup_tenant(request: "HttpRequest") -> "Tenant | None":
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    membership = (
        user.tenant_memberships.select_related("tenant").order_by("created_at").first()
    )
    if membership is None:
        return None
    return membership.tenant
