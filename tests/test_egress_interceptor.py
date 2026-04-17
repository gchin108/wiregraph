from __future__ import annotations

from unittest import mock

import pytest
import requests
from requests.models import PreparedRequest, Response

from wiregraph_apps.common.tenancy import reset_current_tenant, set_current_tenant
from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.egress import interceptor
from wiregraph_apps.egress.models import ExternalService
from wiregraph_apps.egress.signals import egress_pii_leak
from tests.fixtures.factories import TenantFactory


pytestmark = pytest.mark.django_db


def _fake_response(status: int = 200) -> Response:
    resp = Response()
    resp.status_code = status
    resp._content = b""
    return resp


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
    with mock.patch.object(
        requests.Session,
        "send",
        side_effect=lambda self, request, **kw: _fake_response(),
        autospec=True,
    ):
        assert interceptor.install_egress_patch()
        try:
            yield
        finally:
            interceptor.uninstall_egress_patch()


def _post(url: str, body: str) -> PreparedRequest:
    req = requests.Request("POST", url, data=body)
    return req.prepare()


def test_patch_records_external_service_and_pii_event(tenant_ctx, with_patch):
    session = requests.Session()
    session.send(_post("https://api.openai.com/v1/chat", '{"email": "a@b.com"}'))

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


def test_patch_no_pii_still_touches_service(tenant_ctx, with_patch):
    session = requests.Session()
    session.send(_post("https://api.stripe.com/v1/charges", '{"amount": 100}'))

    assert ExternalService.objects.filter(domain="api.stripe.com").exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_internal_header_skips_interception(tenant_ctx, with_patch):
    session = requests.Session()
    prepared = _post("https://hooks.slack.com/svc", '{"email": "a@b.com"}')
    prepared.headers["X-Wiregraph-Internal"] = "1"
    session.send(prepared)

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_no_current_tenant_skips(db, with_patch):
    session = requests.Session()
    session.send(_post("https://api.openai.com/v1/chat", '{"email": "a@b.com"}'))

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_disable_flag_prevents_install(db, settings):
    settings.WIREGRAPH = {"ENABLE_EGRESS_TRACKING": True, "DISABLE_EGRESS_PATCHING": True}
    assert not interceptor.install_egress_patch()


def test_egress_pii_leak_signal_fires(tenant_ctx, with_patch):
    received = []

    def handler(sender, data_event, external_service, **kwargs):
        received.append((data_event, external_service))

    egress_pii_leak.connect(handler)
    try:
        requests.Session().send(_post("https://api.openai.com/v1/chat", '{"email": "a@b.com"}'))
    finally:
        egress_pii_leak.disconnect(handler)

    assert len(received) == 1
    event, svc = received[0]
    assert event.data_asset.name == "email"
    assert svc.domain == "api.openai.com"
