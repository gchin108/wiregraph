"""PII detection middleware must work without DRF on the import path."""

from __future__ import annotations

import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from wiregraph_apps.detection.middleware import PIIDetectionMiddleware
from wiregraph_apps.detection.models import DataEvent
from tests.fixtures.factories import TenantMembershipFactory


pytestmark = pytest.mark.django_db


def test_inbound_detection_runs_with_drf_hidden(no_drf):
    membership = TenantMembershipFactory()
    rf = RequestFactory()

    mw = PIIDetectionMiddleware(lambda r: JsonResponse({"ok": True}))
    req = rf.post(
        "/some/endpoint",
        data={"email": "leaked@example.com"},
        content_type="application/json",
    )
    req.user = membership.user

    response = mw(req)

    assert response.status_code == 200
    assert DataEvent.objects.filter(tenant=membership.tenant).exists()
