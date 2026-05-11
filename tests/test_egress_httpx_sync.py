from __future__ import annotations

import httpx
import pytest
import respx

from wiregraph_apps.common.tenancy import reset_current_tenant, set_current_tenant
from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.egress import interceptor
from wiregraph_apps.egress.models import ExternalService
from wiregraph_apps.egress.signals import egress_pii_leak
from tests.fixtures.factories import TenantFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db):
    return TenantFactory()


@pytest.fixture
def tenant_ctx(tenant):
    token = set_current_tenant(tenant)
    try:
        yield tenant
    finally:
        reset_current_tenant(token)


@pytest.fixture
def with_patch(settings):
    settings.WIREGRAPH = {"ENABLE_EGRESS_TRACKING": True, "DISABLE_EGRESS_PATCHING": False}
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.route(method="POST").respond(200)
        assert "httpx" in interceptor.install_egress_patches()
        try:
            yield
        finally:
            interceptor.uninstall_egress_patches()


def test_httpx_records_external_service_and_pii_event(tenant_ctx, with_patch):
    with httpx.Client() as client:
        client.post("https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}')

    service = ExternalService.objects.get(tenant=tenant_ctx, domain="api.openai.com")
    assert service.first_seen_at is not None

    events = DataEvent.objects.filter(tenant=tenant_ctx, direction="egress")
    assert events.count() == 1
    event = events.get()
    assert event.external_service_id == service.id
    assert event.data_asset.name == "email"
    assert event.endpoint == "/v1/chat"
    assert event.method == "POST"
    assert event.redacted_snippet.startswith("sha256:")


def test_httpx_no_pii_still_touches_service(tenant_ctx, with_patch):
    with httpx.Client() as client:
        client.post("https://api.stripe.com/v1/charges", content=b'{"amount": 100}')

    assert ExternalService.objects.filter(domain="api.stripe.com").exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_httpx_internal_header_skips_interception(tenant_ctx, with_patch):
    with httpx.Client() as client:
        client.post(
            "https://hooks.slack.com/svc",
            content=b'{"email": "a@b.com"}',
            headers={"X-Wiregraph-Internal": "1"},
        )

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_httpx_no_current_tenant_skips(db, with_patch):
    with httpx.Client() as client:
        client.post("https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}')

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_httpx_egress_pii_leak_signal_fires(tenant_ctx, with_patch):
    received = []

    def handler(sender, data_event, external_service, **kwargs):
        received.append((data_event, external_service))

    egress_pii_leak.connect(handler)
    try:
        with httpx.Client() as client:
            client.post("https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}')
    finally:
        egress_pii_leak.disconnect(handler)

    assert len(received) == 1
    event, svc = received[0]
    assert event.data_asset.name == "email"
    assert svc.domain == "api.openai.com"
