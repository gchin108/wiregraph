"""Pure allowlist rule matching.

Hosts pull rules from their store of choice (Django ORM today) and pass them
in as :class:`Rule` instances; this module knows nothing about persistence or
caching. Rule precedence (most → least specific) follows proposal §2:

    1. ``domain + endpoint_prefix``
    2. ``domain``
    3. ``domain_suffix + endpoint_prefix``
    4. ``domain_suffix``
    5. ``endpoint_prefix`` only (legacy)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from wiregraph_core.types import Match


@dataclass(frozen=True)
class Rule:
    asset_name: str
    endpoint_prefix: str = ""
    domain: str = ""
    domain_suffix: str = ""
    id: int | None = None


def _host_matches_suffix(host: str, suffix: str) -> bool:
    if not suffix:
        return False
    host = host.lower()
    s = suffix.lower().lstrip(".")
    return host == s or host.endswith("." + s)


def _specificity(rule: Rule) -> int:
    score = 0
    if rule.domain:
        score += 40
    elif rule.domain_suffix:
        score += 20
    if rule.endpoint_prefix:
        score += 5
    return score


def _rule_matches(rule: Rule, asset_name: str, endpoint: str, host: str) -> bool:
    if rule.asset_name != asset_name:
        return False
    if rule.domain and rule.domain.lower() != host.lower():
        return False
    if rule.domain_suffix and not _host_matches_suffix(host, rule.domain_suffix):
        return False
    if rule.endpoint_prefix and not endpoint.startswith(rule.endpoint_prefix):
        return False
    return True


class AllowlistEngine:
    """Stateless matcher over an in-memory rule set + a global field allowlist."""

    def __init__(
        self,
        rules: Sequence[Rule],
        allowlisted_fields: Iterable[str] = (),
    ):
        self._rules = list(rules)
        self._fields = set(allowlisted_fields)

    def find_matching_rule(
        self, asset_name: str, endpoint: str, host: str = ""
    ) -> Rule | None:
        if asset_name in self._fields:
            return Rule(asset_name=asset_name)
        candidates = [
            r for r in self._rules if _rule_matches(r, asset_name, endpoint, host)
        ]
        if not candidates:
            return None
        candidates.sort(key=_specificity, reverse=True)
        return candidates[0]

    def is_allowlisted(
        self, asset_name: str, endpoint: str, host: str = ""
    ) -> bool:
        return self.find_matching_rule(asset_name, endpoint, host) is not None

    def filter_matches(
        self, matches: Iterable[Match], endpoint: str, host: str = ""
    ) -> list[Match]:
        return [
            m
            for m in matches
            if not self.is_allowlisted(m.asset_name, endpoint, host)
        ]

    def partition_matches(
        self, matches: Iterable[Match], endpoint: str, host: str = ""
    ) -> tuple[list[Match], list[tuple[Match, Rule]], list[Match]]:
        """Three-way split for persistence.

        Returns ``(dropped, allowed, remaining)``:

        * ``dropped`` — matches suppressed by the global field allowlist
          (synthetic Rule with no domain/suffix/endpoint). Do not persist.
        * ``allowed`` — matches that hit a real ``AllowlistRule``; persist
          with ``outcome="expected"`` and the rule attached for audit.
        * ``remaining`` — matches with no allowlist hit; classify normally.
        """
        dropped: list[Match] = []
        allowed: list[tuple[Match, Rule]] = []
        remaining: list[Match] = []
        for m in matches:
            rule = self.find_matching_rule(m.asset_name, endpoint, host)
            if rule is None:
                remaining.append(m)
            elif not rule.domain and not rule.domain_suffix and not rule.endpoint_prefix:
                dropped.append(m)
            else:
                allowed.append((m, rule))
        return dropped, allowed, remaining
