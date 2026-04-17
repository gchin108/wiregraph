"""Reusable DRF view mixins.

``TenantScopedViewSet`` restricts every queryset to the tenant resolved from
the authenticated request. Views that inherit from it never need to worry
about cross-tenant leakage — the base queryset is filtered up front and
cannot be widened by subclasses.
"""

from __future__ import annotations

from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import GenericViewSet

from wiregraph_apps.common.tenancy import resolve_tenant


class TenantScopedMixin:
    def get_tenant(self):
        tenant = resolve_tenant(self.request)
        if tenant is None:
            raise PermissionDenied("No tenant membership for this user.")
        return tenant

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(tenant=self.get_tenant())


class TenantScopedViewSet(TenantScopedMixin, GenericViewSet):
    pass
