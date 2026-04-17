"""Allowlist filtering for PII detection.

A match is suppressed when:
    * its ``asset_name`` is listed in ``WIREGRAPH["ALLOWLISTED_FIELDS"]`` (global)
    * or an ``AllowlistRule`` for the tenant matches both the asset and the
      endpoint (empty ``endpoint_prefix`` matches all endpoints)

Per-tenant rules are cached briefly to avoid a DB hit per request.
"""

from __future__ import annotations

from typing import Iterable

from django.core.cache import cache

from wiregraph_apps.common.conf import get_allowlisted_fields
from wiregraph_apps.detection.regex_scanner import Match

_RULES_CACHE_TTL = 30  # seconds


def _rules_cache_key(tenant) -> str:
    return f"wiregraph:allowlist:{tenant.pk}"


def invalidate_tenant_rules(tenant) -> None:
    cache.delete(_rules_cache_key(tenant))


def _load_rules(tenant) -> list[tuple[str, str]]:
    key = _rules_cache_key(tenant)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from wiregraph_apps.detection.models import AllowlistRule

    rules = list(
        AllowlistRule.objects.filter(tenant=tenant).values_list(
            "asset_name", "endpoint_prefix"
        )
    )
    cache.set(key, rules, _RULES_CACHE_TTL)
    return rules


def is_allowlisted(tenant, asset_name: str, endpoint: str) -> bool:
    if asset_name in set(get_allowlisted_fields()):
        return True
    for rule_asset, rule_prefix in _load_rules(tenant):
        if rule_asset != asset_name:
            continue
        if not rule_prefix:
            return True
        if endpoint.startswith(rule_prefix):
            return True
    return False


def filter_matches(
    tenant, matches: Iterable[Match], endpoint: str
) -> list[Match]:
    return [m for m in matches if not is_allowlisted(tenant, m.asset_name, endpoint)]
