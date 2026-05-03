import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from wiregraph_apps.detection.adapters.allowlist import (
    filter_matches,
    invalidate_tenant_rules,
    is_allowlisted,
)
from wiregraph_apps.detection.models import AllowlistRule
from wiregraph_apps.detection.regex_scanner import Match
from tests.fixtures.factories import TenantFactory, TenantMembershipFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def authed():
    client = APIClient()
    membership = TenantMembershipFactory()
    access = RefreshToken.for_user(membership.user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, membership


def test_global_config_allowlist(settings):
    tenant = TenantFactory()
    settings.WIREGRAPH = {"ALLOWLISTED_FIELDS": ["email"]}
    invalidate_tenant_rules(tenant)
    assert is_allowlisted(tenant, "email", "/login/")
    assert not is_allowlisted(tenant, "ssn", "/login/")


def test_rule_based_allowlist_global_endpoint():
    tenant = TenantFactory()
    AllowlistRule.objects.create(tenant=tenant, asset_name="email", endpoint_prefix="")
    invalidate_tenant_rules(tenant)
    assert is_allowlisted(tenant, "email", "/anything/")


def test_rule_based_allowlist_endpoint_scoped():
    tenant = TenantFactory()
    AllowlistRule.objects.create(
        tenant=tenant, asset_name="email", endpoint_prefix="/auth/"
    )
    invalidate_tenant_rules(tenant)
    assert is_allowlisted(tenant, "email", "/auth/login/")
    assert not is_allowlisted(tenant, "email", "/users/")


def test_filter_matches_drops_allowlisted():
    tenant = TenantFactory()
    AllowlistRule.objects.create(tenant=tenant, asset_name="email", endpoint_prefix="")
    invalidate_tenant_rules(tenant)
    matches = [
        Match("email", 0, 5, "a@b.co", 0.99),
        Match("ssn", 0, 11, "123-45-6789", 0.95),
    ]
    kept = filter_matches(tenant, matches, "/anywhere/")
    assert [m.asset_name for m in kept] == ["ssn"]


def test_api_create_and_list_allowlist(authed):
    client, membership = authed
    resp = client.post(
        "/api/v1/detection/allowlist/",
        {"asset_name": "email", "endpoint_prefix": "/auth/", "reason": "login form"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert AllowlistRule.objects.filter(tenant=membership.tenant).count() == 1

    resp = client.get("/api/v1/detection/allowlist/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_api_allowlist_scoped_to_tenant(authed):
    client, _ = authed
    other = TenantMembershipFactory()
    AllowlistRule.objects.create(
        tenant=other.tenant, asset_name="email", endpoint_prefix=""
    )
    resp = client.get("/api/v1/detection/allowlist/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_api_delete_allowlist_invalidates_cache(authed):
    client, membership = authed
    rule = AllowlistRule.objects.create(
        tenant=membership.tenant, asset_name="email", endpoint_prefix=""
    )
    assert is_allowlisted(membership.tenant, "email", "/x/")

    resp = client.delete(f"/api/v1/detection/allowlist/{rule.id}/")
    assert resp.status_code == 204
    assert not is_allowlisted(membership.tenant, "email", "/x/")
