"""Allowlisted matches persist as ``outcome="expected"`` with the rule attached.

Complements ``test_allowlist.py`` (which exercises the engine and API) and
``test_no_drf/test_persistence.py`` (which exercises the basic write path).
"""

from __future__ import annotations

import pytest

from wiregraph_apps.detection.adapters.allowlist import (
    invalidate_tenant_rules,
    partition_matches,
)
from wiregraph_apps.detection.models import AllowlistRule, DataEvent
from wiregraph_apps.detection.persistence import persist_matches
from wiregraph_apps.detection.regex_scanner import Match
from tests.fixtures.factories import TenantFactory


pytestmark = pytest.mark.django_db


def _email_match(value="user@example.com"):
    return Match("email", 0, len(value), value, 0.99)


def _ssn_match():
    return Match("ssn", 0, 11, "123-45-6789", 0.95)


def test_partition_matches_three_way_split(settings):
    tenant = TenantFactory()
    settings.WIREGRAPH = {"ALLOWLISTED_FIELDS": ["api_key"]}
    AllowlistRule.objects.create(
        tenant=tenant, asset_name="email", endpoint_prefix="/auth/"
    )
    invalidate_tenant_rules(tenant)

    matches = [
        _email_match(),  # allowed by rule
        _ssn_match(),  # remaining
        Match("api_key", 0, 8, "AKIA1234", 0.99),  # dropped (field allowlist)
    ]
    dropped, allowed, remaining = partition_matches(
        tenant, matches, "/auth/login/", ""
    )
    assert [m.asset_name for m in dropped] == ["api_key"]
    assert [m.asset_name for m, _ in allowed] == ["email"]
    assert [m.asset_name for m in remaining] == ["ssn"]
    assert allowed[0][1].id is not None


def test_persist_allowlisted_match_marks_expected_with_rule():
    tenant = TenantFactory()
    rule = AllowlistRule.objects.create(
        tenant=tenant, asset_name="email", endpoint_prefix="/auth/"
    )
    invalidate_tenant_rules(tenant)

    events = persist_matches(
        tenant=tenant,
        matches=[_email_match()],
        direction="inbound",
        endpoint="/auth/login/",
        method="POST",
        detection_method="regex",
    )
    assert len(events) == 1
    ev = events[0]
    assert ev.outcome == "expected"
    assert ev.allowlist_rule_id == rule.id
    assert ev.decision_reason == f"allowlist:{rule.id}"


def test_persist_field_allowlist_drops_entirely(settings):
    tenant = TenantFactory()
    settings.WIREGRAPH = {"ALLOWLISTED_FIELDS": ["email"]}
    invalidate_tenant_rules(tenant)

    events = persist_matches(
        tenant=tenant,
        matches=[_email_match()],
        direction="inbound",
        endpoint="/auth/login/",
        method="POST",
        detection_method="regex",
    )
    assert events == []
    assert not DataEvent.objects.filter(tenant=tenant).exists()


def test_per_asset_allowlist_decision():
    """Allowlist decisions are per-asset: a single request with one
    allowlisted asset and one non-allowlisted asset yields two rows with
    independent outcomes."""
    tenant = TenantFactory()
    AllowlistRule.objects.create(
        tenant=tenant, asset_name="email", endpoint_prefix="/auth/"
    )
    invalidate_tenant_rules(tenant)

    events = persist_matches(
        tenant=tenant,
        matches=[_email_match(), _ssn_match()],
        direction="inbound",
        endpoint="/auth/login/",
        method="POST",
        detection_method="regex",
    )
    by_asset = {e.data_asset.name: e for e in events}
    assert by_asset["email"].outcome == "expected"
    assert by_asset["email"].allowlist_rule_id is not None
    assert by_asset["email"].decision_reason.startswith("allowlist:")
    # SSN row is classified normally (no allowlist attribution); the outcome
    # depends on sink classification, but it must NOT carry an allowlist
    # rule reference.
    assert by_asset["ssn"].allowlist_rule_id is None
    assert not by_asset["ssn"].decision_reason.startswith("allowlist:")
