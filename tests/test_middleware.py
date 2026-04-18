import json

import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from wiregraph_apps.detection.middleware import PIIDetectionMiddleware
from wiregraph_apps.detection.models import DataEvent
from tests.fixtures.factories import TenantMembershipFactory, UserFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def membership(db):
    return TenantMembershipFactory()


@pytest.fixture
def user_with_tenant(membership):
    return membership.user


@pytest.fixture
def ok_view():
    return lambda request: JsonResponse({"ok": True})


@pytest.fixture
def leaky_view():
    return lambda request: JsonResponse({"email": "leaked@example.com"})


def _authed_post(rf, user, path, body, content_type="application/json"):
    req = rf.post(path, data=body, content_type=content_type)
    req.user = user
    return req


def test_inbound_regex_creates_event(rf, user_with_tenant, ok_view):
    mw = PIIDetectionMiddleware(ok_view)
    req = _authed_post(
        rf,
        user_with_tenant,
        "/api/orders/",
        json.dumps({"email": "jane@example.com"}),
    )
    mw(req)
    events = DataEvent.objects.filter(direction="inbound")
    assert events.count() == 1
    assert events.first().data_asset.name == "email"


def test_outbound_regex_creates_event(rf, user_with_tenant, leaky_view):
    mw = PIIDetectionMiddleware(leaky_view)
    req = rf.get("/api/profile/")
    req.user = user_with_tenant
    mw(req)
    events = DataEvent.objects.filter(direction="outbound")
    assert events.count() == 1
    assert events.first().data_asset.name == "email"


def test_inbound_and_outbound_share_request_id(rf, user_with_tenant, leaky_view):
    mw = PIIDetectionMiddleware(leaky_view)
    req = _authed_post(
        rf,
        user_with_tenant,
        "/api/echo/",
        json.dumps({"email": "in@example.com"}),
    )
    mw(req)
    ids = set(DataEvent.objects.values_list("request_id", flat=True))
    assert len(ids) == 1
    assert next(iter(ids))  # non-empty


def test_excluded_path_skips_scan(rf, user_with_tenant, leaky_view, settings):
    settings.WIREGRAPH = {**getattr(settings, "WIREGRAPH", {}), "EXCLUDED_PATHS": ["/health"]}
    mw = PIIDetectionMiddleware(leaky_view)
    req = rf.get("/health/live")
    req.user = user_with_tenant
    mw(req)
    assert DataEvent.objects.count() == 0


def test_admin_path_auto_excluded(rf, user_with_tenant, leaky_view):
    mw = PIIDetectionMiddleware(leaky_view)
    req = rf.get("/admin/wiregraph_detection/dataevent/")
    req.user = user_with_tenant
    mw(req)
    assert DataEvent.objects.count() == 0


def test_admin_auto_exclude_can_be_disabled(rf, user_with_tenant, leaky_view, settings):
    settings.WIREGRAPH = {**getattr(settings, "WIREGRAPH", {}), "AUTO_EXCLUDE_ADMIN": False}
    mw = PIIDetectionMiddleware(leaky_view)
    req = rf.get("/admin/wiregraph_detection/dataevent/")
    req.user = user_with_tenant
    mw(req)
    assert DataEvent.objects.count() > 0


def test_sampling_rate_zero_skips_scan(rf, user_with_tenant, leaky_view, settings):
    settings.WIREGRAPH = {**getattr(settings, "WIREGRAPH", {}), "SAMPLING_RATE": 0.0}
    mw = PIIDetectionMiddleware(leaky_view)
    req = rf.get("/api/anything/")
    req.user = user_with_tenant
    mw(req)
    assert DataEvent.objects.count() == 0


def test_max_body_size_skips_large_payloads(rf, user_with_tenant, ok_view, settings):
    settings.WIREGRAPH = {**getattr(settings, "WIREGRAPH", {}), "MAX_BODY_SIZE": 32}
    mw = PIIDetectionMiddleware(ok_view)
    big_body = json.dumps({"email": "jane@example.com", "pad": "x" * 200})
    req = _authed_post(rf, user_with_tenant, "/api/big/", big_body)
    mw(req)
    assert DataEvent.objects.filter(direction="inbound").count() == 0


def test_anonymous_request_skipped(rf, ok_view, db):
    from django.contrib.auth.models import AnonymousUser

    mw = PIIDetectionMiddleware(ok_view)
    req = _authed_post(
        rf,
        AnonymousUser(),
        "/api/orders/",
        json.dumps({"email": "jane@example.com"}),
    )
    mw(req)
    assert DataEvent.objects.count() == 0


def test_tenant_isolation(rf, ok_view):
    m1 = TenantMembershipFactory()
    m2 = TenantMembershipFactory()
    mw = PIIDetectionMiddleware(ok_view)

    req1 = _authed_post(rf, m1.user, "/api/x/", json.dumps({"email": "a@a.com"}))
    mw(req1)
    req2 = _authed_post(rf, m2.user, "/api/x/", json.dumps({"email": "b@b.com"}))
    mw(req2)

    assert DataEvent.objects.filter(tenant=m1.tenant).count() == 1
    assert DataEvent.objects.filter(tenant=m2.tenant).count() == 1
    assert DataEvent.objects.filter(tenant=m1.tenant).first().request_id != \
        DataEvent.objects.filter(tenant=m2.tenant).first().request_id


def test_multiple_matches_coalesce_per_asset(rf, user_with_tenant):
    def view(request):
        return JsonResponse({
            "users": [
                {"email": "a@example.com", "phone": "415-555-0100"},
                {"email": "b@example.com", "phone": "415-555-0101"},
                {"email": "c@example.com", "phone": "415-555-0102"},
            ],
        })

    mw = PIIDetectionMiddleware(view)
    req = rf.get("/api/users/")
    req.user = user_with_tenant
    mw(req)

    events = DataEvent.objects.filter(direction="outbound")
    assert events.count() == 2
    by_asset = {e.data_asset.name: e for e in events}
    assert by_asset["email"].match_count == 3
    assert by_asset["phone_us"].match_count == 3


def test_non_scannable_content_type_skipped(rf, user_with_tenant, ok_view):
    mw = PIIDetectionMiddleware(ok_view)
    req = rf.post(
        "/api/upload/",
        data=b"\x00\x01\x02 jane@example.com",
        content_type="application/octet-stream",
    )
    req.user = user_with_tenant
    mw(req)
    assert DataEvent.objects.filter(direction="inbound").count() == 0
