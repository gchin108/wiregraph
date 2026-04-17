import json

import pytest
from django.test import RequestFactory

from wiregraph_apps.detection.middleware import PIIDetectionMiddleware
from wiregraph_apps.detection.models import DataAsset, DataEvent
from wiregraph_apps.detection.signals import new_data_asset_discovered, pii_detected
from tests.fixtures.factories import TenantMembershipFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def rf():
    return RequestFactory()


def _signal_capture(signal):
    captured = []

    def handler(sender, **kwargs):
        captured.append(kwargs)

    signal.connect(handler, weak=False)
    return captured, handler


def _run_middleware(rf, user):
    mw = PIIDetectionMiddleware(get_response=lambda request: _ok())
    req = rf.post(
        "/api/users/",
        data=json.dumps({"email": "alice@example.com"}),
        content_type="application/json",
    )
    req.user = user
    return mw(req)


def _ok():
    from django.http import HttpResponse

    return HttpResponse("ok", content_type="text/plain")


def test_pii_detected_signal_fires(rf):
    membership = TenantMembershipFactory()
    captured, handler = _signal_capture(pii_detected)
    try:
        _run_middleware(rf, membership.user)
    finally:
        pii_detected.disconnect(handler)

    assert len(captured) == 1
    assert captured[0]["data_event"].data_asset.name == "email"
    assert captured[0]["request"] is not None


def test_new_data_asset_signal_fires_once_per_new_asset(rf):
    membership = TenantMembershipFactory()
    captured, handler = _signal_capture(new_data_asset_discovered)
    try:
        _run_middleware(rf, membership.user)
        _run_middleware(rf, membership.user)  # second time, asset already exists
    finally:
        new_data_asset_discovered.disconnect(handler)

    # Signal must only fire the first time the asset was created.
    assert len(captured) == 1
    assert captured[0]["data_asset"].name == "email"
    assert captured[0]["tenant"].pk == membership.tenant.pk
