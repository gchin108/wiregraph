"""Allowlist filtering for PII detection.

A match is suppressed when:
    * its ``asset_name`` is listed in ``WIREGRAPH["ALLOWLISTED_FIELDS"]`` (global)
    * or an ``AllowlistRule`` for the tenant matches the asset and the host +
      endpoint. Empty host / endpoint fields match anything.

Rule match precedence (most → least specific, per proposal §2):
    1. ``domain + endpoint_prefix``
    2. ``domain``
    3. ``domain_suffix + endpoint_prefix``
    4. ``domain_suffix``
    5. ``endpoint_prefix`` only (legacy)

Per-tenant rules are cached briefly to avoid a DB hit per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.cache import cache

from wiregraph_apps.common.conf import get_allowlisted_fields
from wiregraph_apps.detection.regex_scanner import Match

_RULES_CACHE_TTL = 30  # seconds


@dataclass(frozen=True)
class _Rule:
    asset_name: str
    endpoint_prefix: str
    domain: str
    domain_suffix: str


def _rules_cache_key(tenant) -> str:
    return f"wiregraph:allowlist:{tenant.pk}"


def invalidate_tenant_rules(tenant) -> None:
    cache.delete(_rules_cache_key(tenant))


def _load_rules(tenant) -> list[_Rule]:
    key = _rules_cache_key(tenant)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from wiregraph_apps.detection.models import AllowlistRule

    rules = [
        _Rule(
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


def _host_matches_suffix(host: str, suffix: str) -> bool:
    if not suffix:
        return False
    host = host.lower()
    s = suffix.lower().lstrip(".")
    return host == s or host.endswith("." + s)


def _specificity(rule: _Rule) -> int:
    """Higher = more specific. See precedence list in module docstring."""
    score = 0
    if rule.domain:
        score += 40
    elif rule.domain_suffix:
        score += 20
    if rule.endpoint_prefix:
        score += 5
    return score


def _rule_matches(rule: _Rule, asset_name: str, endpoint: str, host: str) -> bool:
    if rule.asset_name != asset_name:
        return False
    if rule.domain and rule.domain.lower() != host.lower():
        return False
    if rule.domain_suffix and not _host_matches_suffix(host, rule.domain_suffix):
        return False
    if rule.endpoint_prefix and not endpoint.startswith(rule.endpoint_prefix):
        return False
    return True


def find_matching_rule(
    tenant, asset_name: str, endpoint: str, host: str = ""
) -> _Rule | None:
    """Return the most-specific matching rule, or ``None``."""
    if asset_name in set(get_allowlisted_fields()):
        # Treat global config as an implicit manual rule.
        return _Rule(
            asset_name=asset_name,
            endpoint_prefix="",
            domain="",
            domain_suffix="",
        )

    candidates = [
        r
        for r in _load_rules(tenant)
        if _rule_matches(r, asset_name, endpoint, host)
    ]
    if not candidates:
        return None
    candidates.sort(key=_specificity, reverse=True)
    return candidates[0]


def is_allowlisted(
    tenant, asset_name: str, endpoint: str, host: str = ""
) -> bool:
    return find_matching_rule(tenant, asset_name, endpoint, host) is not None


def filter_matches(
    tenant, matches: Iterable[Match], endpoint: str, host: str = ""
) -> list[Match]:
    return [m for m in matches if not is_allowlisted(tenant, m.asset_name, endpoint, host)]
