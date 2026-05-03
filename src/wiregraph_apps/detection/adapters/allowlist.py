"""Django adapter for :mod:`wiregraph_core.allowlist`.

Loads ``AllowlistRule`` rows for the tenant (with a brief per-tenant cache),
combines them with ``WIREGRAPH["ALLOWLISTED_FIELDS"]``, and delegates rule
matching to the pure :class:`AllowlistEngine`.
"""

from __future__ import annotations

from typing import Iterable

from wiregraph_apps.common.conf import get_allowlisted_fields
from wiregraph_apps.detection.adapters.cache import get_cache
from wiregraph_core.allowlist import AllowlistEngine, Rule
from wiregraph_core.types import Match

_RULES_CACHE_TTL = 30  # seconds


def _rules_cache_key(tenant) -> str:
    return f"wiregraph:allowlist:{tenant.pk}"


def invalidate_tenant_rules(tenant) -> None:
    get_cache().delete(_rules_cache_key(tenant))


def _load_rules(tenant) -> list[Rule]:
    cache = get_cache()
    key = _rules_cache_key(tenant)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from wiregraph_apps.detection.models import AllowlistRule

    rules = [
        Rule(
            asset_name=a,
            endpoint_prefix=ep or "",
            domain=d or "",
            domain_suffix=ds or "",
        )
        for a, ep, d, ds in AllowlistRule.objects.filter(tenant=tenant).values_list(
            "asset_name", "endpoint_prefix", "domain", "domain_suffix"
        )
    ]
    cache.set(key, rules, _RULES_CACHE_TTL)
    return rules


def _engine(tenant) -> AllowlistEngine:
    return AllowlistEngine(_load_rules(tenant), get_allowlisted_fields())


def find_matching_rule(
    tenant, asset_name: str, endpoint: str, host: str = ""
) -> Rule | None:
    return _engine(tenant).find_matching_rule(asset_name, endpoint, host)


def is_allowlisted(
    tenant, asset_name: str, endpoint: str, host: str = ""
) -> bool:
    return _engine(tenant).is_allowlisted(asset_name, endpoint, host)


def filter_matches(
    tenant, matches: Iterable[Match], endpoint: str, host: str = ""
) -> list[Match]:
    return _engine(tenant).filter_matches(matches, endpoint, host)
