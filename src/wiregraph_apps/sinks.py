"""Django-aware sink resolver.

Layers tenant ``SinkCatalogOverride`` rows + ``WIREGRAPH["SINK_OVERRIDES"]``
on top of the framework-agnostic catalog in :mod:`wiregraph_core.sinks` and
hands the ordered catalog list to :func:`wiregraph_core.sinks.resolve_from_catalogs`.

Public names (``CATEGORY_DEFAULTS``, ``BUILTIN_CATALOG``, ``ASSET_SENSITIVITY``,
``SinkInfo``, ``sensitivity_for``, ``resolve_sink``) are kept stable so existing
imports and tests don't move.
"""

from __future__ import annotations

from wiregraph_core.sinks import (
    ASSET_SENSITIVITY,
    BUILTIN_CATALOG,
    CATEGORY_DEFAULTS,
    SinkInfo,
    resolve_from_catalogs,
    sensitivity_for,
)

__all__ = [
    "ASSET_SENSITIVITY",
    "BUILTIN_CATALOG",
    "CATEGORY_DEFAULTS",
    "SinkInfo",
    "resolve_sink",
    "sensitivity_for",
]


def _tenant_overrides(tenant) -> dict:
    if tenant is None:
        return {}
    try:
        from wiregraph_apps.egress.models import SinkCatalogOverride

        return {
            row.domain_suffix: {
                "category": row.category,
                "trust_tier": row.trust_tier,
                "accepts_assets": row.accepts_assets or None,
                "display_name": row.display_name,
            }
            for row in SinkCatalogOverride.objects.filter(tenant=tenant)
        }
    except Exception:  # pragma: no cover — model may not yet be migrated in tests
        return {}


def resolve_sink(host: str, tenant=None) -> SinkInfo:
    """Resolve a host using DB → settings → built-in precedence."""
    from wiregraph_apps.common.conf import get_sink_overrides

    catalogs = [
        _tenant_overrides(tenant),
        get_sink_overrides() or {},
        BUILTIN_CATALOG,
    ]
    return resolve_from_catalogs(host, catalogs)
