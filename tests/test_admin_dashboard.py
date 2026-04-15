import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core_apps.egress.models import ExternalService
from tests.fixtures.factories import (
    DataAssetFactory,
    DataEventFactory,
    TenantMembershipFactory,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create_user(username="admin1", password="pw", is_staff=True)
    membership = TenantMembershipFactory(user=user)
    client = Client()
    client.force_login(user)
    return client, membership


def test_dashboard_renders_empty(staff_client):
    client, _ = staff_client
    resp = client.get("/admin/wiregraph/dashboard/")
    assert resp.status_code == 200
    assert b"No PII flows observed" in resp.content


def test_dashboard_includes_observed_flows(staff_client):
    client, membership = staff_client
    asset = DataAssetFactory(tenant=membership.tenant, name="email", label="Email")
    service = ExternalService.objects.create(
        tenant=membership.tenant,
        domain="api.openai.com",
        name="OpenAI",
        first_seen_at="2026-04-01T00:00:00Z",
        last_seen_at="2026-04-10T00:00:00Z",
    )
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset, direction="inbound",
        endpoint="/api/users/",
    )
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset, direction="egress",
        endpoint="/v1/chat/completions", external_service=service,
    )

    resp = client.get("/admin/wiregraph/dashboard/?format=json")
    assert resp.status_code == 200
    body = resp.json()
    labels = [e["label"] for e in body["endpoints"]]
    assert "/api/users/" in labels
    assert any(s["label"] == "OpenAI" for s in body["services"])
    assert len(body["edges"]) == 2


def test_dashboard_requires_staff():
    User = get_user_model()
    User.objects.create_user(username="u1", password="pw", is_staff=False)
    client = Client()
    client.login(username="u1", password="pw")
    resp = client.get("/admin/wiregraph/dashboard/")
    # admin_view redirects non-staff users to login
    assert resp.status_code in (302, 403)
