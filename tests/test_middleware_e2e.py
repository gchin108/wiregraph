"""End-to-end test: middleware registered in MIDDLEWARE observes traffic
through the real Django request pipeline, authenticated via JWT."""

import json

import pytest
from django.http import JsonResponse
from django.urls import path
from rest_framework_simplejwt.tokens import RefreshToken

from core_apps.detection.models import DataEvent
from tests.fixtures.factories import TenantMembershipFactory


pytestmark = pytest.mark.django_db


def _echo_view(request):
    return JsonResponse({"seen": "ok", "email": "leaked@example.com"})


urlpatterns = [
    path("e2e/echo/", _echo_view),
]


@pytest.fixture
def jwt_client(client):
    membership = TenantMembershipFactory()
    access = RefreshToken.for_user(membership.user).access_token
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    return client, membership


def test_jwt_authed_pipeline_records_inbound_and_outbound(jwt_client, settings):
    settings.ROOT_URLCONF = __name__
    client, membership = jwt_client

    response = client.post(
        "/e2e/echo/",
        data=json.dumps({"email": "user@example.com"}),
        content_type="application/json",
    )
    assert response.status_code == 200

    tenant_events = DataEvent.objects.filter(tenant=membership.tenant)
    directions = set(tenant_events.values_list("direction", flat=True))
    assert directions == {"inbound", "outbound"}

    request_ids = set(tenant_events.values_list("request_id", flat=True))
    assert len(request_ids) == 1

    for event in tenant_events:
        assert "user@example.com" not in event.redacted_snippet
        assert "leaked@example.com" not in event.redacted_snippet


def test_invalid_jwt_skips_scanning(client, settings):
    settings.ROOT_URLCONF = __name__
    client.defaults["HTTP_AUTHORIZATION"] = "Bearer not-a-real-token"
    response = client.post(
        "/e2e/echo/",
        data=json.dumps({"email": "user@example.com"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert DataEvent.objects.count() == 0
