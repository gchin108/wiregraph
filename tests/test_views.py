import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from wiregraph_apps.detection.models import DataAsset
from tests.fixtures.factories import (
    DataAssetFactory,
    DataEventFactory,
    TenantMembershipFactory,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authed(api_client):
    membership = TenantMembershipFactory()
    access = RefreshToken.for_user(membership.user).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api_client, membership


def test_events_list_requires_auth(api_client):
    response = api_client.get("/api/v1/detection/events/")
    assert response.status_code == 401


def test_events_list_returns_tenant_events_only(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    DataEventFactory(tenant=membership.tenant, data_asset=asset, direction="inbound")
    DataEventFactory(tenant=membership.tenant, data_asset=asset, direction="outbound")

    other = TenantMembershipFactory()
    other_asset = DataAssetFactory(tenant=other.tenant, name="email")
    DataEventFactory(tenant=other.tenant, data_asset=other_asset)

    response = client.get("/api/v1/detection/events/")
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_events_filter_by_direction(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    DataEventFactory(tenant=membership.tenant, data_asset=asset, direction="inbound")
    DataEventFactory(tenant=membership.tenant, data_asset=asset, direction="outbound")

    response = client.get("/api/v1/detection/events/?direction=outbound")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["direction"] == "outbound"


def test_events_filter_by_asset_name(authed):
    client, membership = authed
    email = DataAssetFactory(tenant=membership.tenant, name="email")
    ssn = DataAssetFactory(tenant=membership.tenant, name="ssn")
    DataEventFactory(tenant=membership.tenant, data_asset=email)
    DataEventFactory(tenant=membership.tenant, data_asset=ssn)

    response = client.get("/api/v1/detection/events/?data_asset=ssn")
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["data_asset"] == "ssn"


def test_event_detail(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    event = DataEventFactory(tenant=membership.tenant, data_asset=asset)

    response = client.get(f"/api/v1/detection/events/{event.id}/")
    assert response.status_code == 200
    assert response.json()["id"] == str(event.id)


def test_event_detail_includes_json_path(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    event = DataEventFactory(
        tenant=membership.tenant,
        data_asset=asset,
        json_path="body.customer.email",
    )

    body = client.get(f"/api/v1/detection/events/{event.id}/").json()
    assert body["json_path"] == "body.customer.email"


def test_event_detail_blocks_cross_tenant(authed):
    client, _membership = authed
    other = TenantMembershipFactory()
    other_asset = DataAssetFactory(tenant=other.tenant, name="email")
    other_event = DataEventFactory(tenant=other.tenant, data_asset=other_asset)

    response = client.get(f"/api/v1/detection/events/{other_event.id}/")
    assert response.status_code == 404


def test_assets_list(authed):
    client, membership = authed
    DataAssetFactory(tenant=membership.tenant, name="email")
    DataAssetFactory(tenant=membership.tenant, name="ssn")
    TenantMembershipFactory()  # unrelated tenant, no asset

    response = client.get("/api/v1/detection/assets/")
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_summary_stats(authed):
    client, membership = authed
    email = DataAssetFactory(tenant=membership.tenant, name="email")
    DataEventFactory(tenant=membership.tenant, data_asset=email, direction="inbound", endpoint="/a/")
    DataEventFactory(tenant=membership.tenant, data_asset=email, direction="outbound", endpoint="/b/")
    DataEventFactory(tenant=membership.tenant, data_asset=email, direction="outbound", endpoint="/b/")

    response = client.get("/api/v1/detection/stats/summary/")
    assert response.status_code == 200
    body = response.json()
    assert body["event_count"] == 3
    assert body["asset_count"] == 1
    assert body["endpoint_count"] == 2
    assert body["by_direction"] == {"inbound": 1, "outbound": 2}
    assert body["by_asset"] == {"email": 3}


def test_endpoint_nodes_list_groups_by_service_endpoint_method(authed):
    client, membership = authed
    email = DataAssetFactory(tenant=membership.tenant, name="email")
    ssn = DataAssetFactory(tenant=membership.tenant, name="ssn")
    DataEventFactory(
        tenant=membership.tenant, data_asset=email,
        direction="outbound", endpoint="/v1/chat", method="POST", outcome="suspicious",
    )
    DataEventFactory(
        tenant=membership.tenant, data_asset=ssn,
        direction="outbound", endpoint="/v1/chat", method="POST", outcome="prohibited",
    )
    DataEventFactory(
        tenant=membership.tenant, data_asset=email,
        direction="outbound", endpoint="/v1/embeddings", method="POST", outcome="acceptable",
    )
    # inbound events must not appear as endpoint nodes
    DataEventFactory(
        tenant=membership.tenant, data_asset=email,
        direction="inbound", endpoint="/signup", method="POST",
    )

    response = client.get("/api/v1/detection/endpoint-nodes/")
    assert response.status_code == 200
    nodes = response.json()
    assert len(nodes) == 2
    by_endpoint = {n["endpoint"]: n for n in nodes}
    chat = by_endpoint["/v1/chat"]
    assert chat["worst_outcome"] == "prohibited"
    assert chat["event_count"] == 2
    assert {a["name"] for a in chat["assets"]} == {"email", "ssn"}


def test_endpoint_node_events_drilldown(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="outbound", endpoint="/v1/chat", method="POST",
    )
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="outbound", endpoint="/v1/other", method="POST",
    )

    nodes = client.get("/api/v1/detection/endpoint-nodes/").json()
    chat_id = next(n["id"] for n in nodes if n["endpoint"] == "/v1/chat")

    response = client.get(f"/api/v1/detection/endpoint-nodes/{chat_id}/events/")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["endpoint"] == "/v1/chat"


def test_endpoint_node_unknown_returns_404(authed):
    client, _ = authed
    import base64
    bogus = base64.urlsafe_b64encode(b"|GET|/missing").decode().rstrip("=")
    response = client.get(f"/api/v1/detection/endpoint-nodes/{bogus}/")
    assert response.status_code == 404


def test_event_trace_returns_inbound_outbound_and_asset(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    inbound_a = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="inbound", endpoint="/signup", request_id="req-1",
    )
    inbound_b = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="inbound", endpoint="/signup", request_id="req-1",
    )
    outbound = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="outbound", endpoint="/v1/chat", request_id="req-1",
    )
    # Unrelated event with different request_id must not appear.
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="inbound", endpoint="/other", request_id="req-2",
    )

    response = client.get(f"/api/v1/detection/events/{outbound.id}/trace/")
    assert response.status_code == 200
    body = response.json()
    assert body["outbound"]["id"] == str(outbound.id)
    assert {row["id"] for row in body["inbound"]} == {str(inbound_a.id), str(inbound_b.id)}
    assert body["asset"]["name"] == "email"


def test_event_trace_from_inbound_finds_outbound(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    inbound = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="inbound", request_id="req-9",
    )
    outbound = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="outbound", request_id="req-9",
    )

    body = client.get(f"/api/v1/detection/events/{inbound.id}/trace/").json()
    assert body["outbound"]["id"] == str(outbound.id)
    assert {row["id"] for row in body["inbound"]} == {str(inbound.id)}


def test_event_trace_blank_request_id_has_no_inbound(authed):
    client, membership = authed
    asset = DataAssetFactory(tenant=membership.tenant, name="email")
    DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="inbound", request_id="",
    )
    outbound = DataEventFactory(
        tenant=membership.tenant, data_asset=asset,
        direction="outbound", request_id="",
    )

    body = client.get(f"/api/v1/detection/events/{outbound.id}/trace/").json()
    assert body["inbound"] == []
    assert body["outbound"]["id"] == str(outbound.id)


def test_event_trace_blocks_cross_tenant(authed):
    client, _membership = authed
    other = TenantMembershipFactory()
    other_asset = DataAssetFactory(tenant=other.tenant, name="email")
    other_event = DataEventFactory(
        tenant=other.tenant, data_asset=other_asset, direction="outbound",
    )
    response = client.get(f"/api/v1/detection/events/{other_event.id}/trace/")
    assert response.status_code == 404


def test_event_trace_unknown_returns_404(authed):
    client, _ = authed
    import uuid
    response = client.get(f"/api/v1/detection/events/{uuid.uuid4()}/trace/")
    assert response.status_code == 404


def test_user_without_tenant_gets_403(api_client):
    from tests.fixtures.factories import UserFactory

    user = UserFactory()
    access = RefreshToken.for_user(user).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = api_client.get("/api/v1/detection/events/")
    assert response.status_code == 403
