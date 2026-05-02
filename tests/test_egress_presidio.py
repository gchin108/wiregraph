"""Phase 4 — Presidio parity on the egress path (§6).

The interceptor must enqueue ``scan_payload_async`` alongside the synchronous
regex scan so names/addresses leaking to LLMs are detected, not just
structured PII.
"""
from __future__ import annotations

from unittest import mock

import pytest
import requests
from django.test import override_settings
from requests.models import PreparedRequest, Response

from wiregraph_apps.common.tenancy import reset_current_tenant, set_current_tenant
from wiregraph_apps.detection import tasks
from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.detection.regex_scanner import Match
from wiregraph_apps.egress import interceptor
from wiregraph_apps.egress.models import ExternalService
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
    settings.WIREGRAPH = {
        "ENABLE_EGRESS_TRACKING": True,
        "DISABLE_EGRESS_PATCHING": False,
        "ENABLE_PRESIDIO": True,
    }
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


def test_egress_enqueues_presidio_with_service_id(tenant_ctx, with_patch):
    session = requests.Session()
    with mock.patch("wiregraph_apps.detection.tasks.scan_payload_async") as task:
        session.send(_post("https://api.openai.com/v1/chat", '{"msg": "hello Jane Doe"}'))

    service = ExternalService.objects.get(tenant=tenant_ctx, domain="api.openai.com")
    assert task.delay.call_count == 1
    kwargs = task.delay.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_ctx.pk
    assert kwargs["direction"] == "egress"
    assert kwargs["endpoint"] == "/v1/chat"
    assert kwargs["method"] == "POST"
    assert kwargs["external_service_id"] == service.pk


@override_settings(WIREGRAPH={
    "ENABLE_EGRESS_TRACKING": True,
    "DISABLE_EGRESS_PATCHING": False,
    "ENABLE_PRESIDIO": False,
})
def test_egress_does_not_enqueue_when_presidio_disabled(tenant_ctx):
    with mock.patch.object(
        requests.Session,
        "send",
        side_effect=lambda self, request, **kw: _fake_response(),
        autospec=True,
    ):
        assert interceptor.install_egress_patch()
        try:
            with mock.patch("wiregraph_apps.detection.tasks.scan_payload_async") as task:
                requests.Session().send(
                    _post("https://api.openai.com/v1/chat", '{"msg": "hi"}')
                )
            task.delay.assert_not_called()
        finally:
            interceptor.uninstall_egress_patch()


def test_egress_no_enqueue_when_body_empty(tenant_ctx, with_patch):
    session = requests.Session()
    # GET with no body — _extract_body returns None, so no enqueue.
    with mock.patch("wiregraph_apps.detection.tasks.scan_payload_async") as task:
        req = requests.Request("GET", "https://api.openai.com/v1/chat").prepare()
        session.send(req)
    task.delay.assert_not_called()


def test_task_run_persists_egress_presidio_event(tenant):
    """_run threads external_service_id through persist_matches so the
    egress presidio event lands with the sink attached and is classified."""
    from django.utils import timezone

    now = timezone.now()
    service = ExternalService.objects.create(
        tenant=tenant,
        domain="api.openai.com",
        name="OpenAI",
        category="llm",
        trust_tier="known",
        accepts_assets=[],
        first_seen_at=now,
        last_seen_at=now,
    )

    fake_matches = [Match("person_name", 0, 8, "Jane Doe", 0.95)]
    with override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": True}):
        with mock.patch(
            "wiregraph_core.scanner.presidio.PresidioScanner.scan",
            return_value=fake_matches,
        ):
            result = tasks._run(
                tenant_id=tenant.pk,
                text="Jane Doe was here",
                direction="egress",
                endpoint="/v1/chat",
                method="POST",
                request_id="",
                external_service_id=service.pk,
            )

    assert result == {"persisted": 1}
    event = DataEvent.objects.get(detection_method="presidio", direction="egress")
    assert event.external_service_id == service.pk
    assert event.data_asset.name == "person_name"
    # llm + medium-sensitivity PII under strict policy → prohibited.
    assert event.outcome == "prohibited"
    assert event.decision_reason.startswith("policy:")
