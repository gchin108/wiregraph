"""Pluggable tenant resolvers.

By default WireGraph resolves the active tenant by walking
``request.user.tenant_memberships`` and picking the oldest membership. Projects
whose user model stores tenancy differently (an ``active_tenant`` FK on the
user, a tenant slug in the subdomain, a header set by an API gateway, …) can
override this via the ``WIREGRAPH["TENANT_RESOLVER"]`` setting, which takes a
dotted path to a callable ``(HttpRequest) -> Tenant | None``.

The configured resolver is cached at module level and invalidated automatically
when Django fires ``setting_changed`` (so tests using ``override_settings`` see
a fresh resolver on every override).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from django.http import HttpRequest

    from wiregraph_apps.tenants.models import Tenant


TenantResolver = Callable[["HttpRequest"], Optional["Tenant"]]

_cached_resolver: TenantResolver | None = None


def default(request: "HttpRequest") -> "Tenant | None":
    """Default resolver: first ``TenantMembership`` for the authenticated user.

    Returns ``None`` for anonymous users or users without any membership.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    membership = (
        user.tenant_memberships.select_related("tenant").order_by("created_at").first()
    )
    if membership is None:
        return None
    return membership.tenant


def load_configured() -> TenantResolver:
    """Return the resolver configured via ``WIREGRAPH["TENANT_RESOLVER"]``.

    Cached after first lookup. Cleared automatically on ``setting_changed``.
    """
    global _cached_resolver
    if _cached_resolver is not None:
        return _cached_resolver

    # Local import to keep this module importable before Django app registry
    # is ready (e.g. during ``manage.py`` startup).
    from wiregraph_apps.common.conf import get_config

    dotted = get_config("TENANT_RESOLVER")
    _cached_resolver = import_string(dotted)
    return _cached_resolver


@receiver(setting_changed)
def _invalidate_on_setting_change(sender, setting, **kwargs):
    if setting == "WIREGRAPH":
        global _cached_resolver
        _cached_resolver = None
