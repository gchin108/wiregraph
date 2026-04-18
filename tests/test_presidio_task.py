import json
from unittest.mock import patch

import pytest
from django.http import JsonResponse
from django.test import RequestFactory, override_settings

from wiregraph_apps.detection.middleware import PIIDetectionMiddleware
from wiregraph_apps.detection.regex_scanner import Match
from tests.fixtures.factories import TenantMembershipFactory


pytestmark = pytest.mark.django_db


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def membership(db):
    return TenantMembershipFactory()


def _post(rf, user, body):
    req = rf.post("/api/x/", data=body, content_type="application/json")
    req.user = user
    return req


@override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": False})
def test_middleware_does_not_enqueue_when_presidio_disabled(rf, membership):
    view = lambda r: JsonResponse({"ok": True})
    mw = PIIDetectionMiddleware(view)
    with patch("wiregraph_apps.detection.tasks.scan_payload_async") as task:
        mw(_post(rf, membership.user, json.dumps({"email": "a@b.com"})))
    task.delay.assert_not_called()


@override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": True})
def test_middleware_enqueues_when_presidio_enabled(rf, membership):
    view = lambda r: JsonResponse({"ok": True})
    mw = PIIDetectionMiddleware(view)
    with patch("wiregraph_apps.detection.tasks.scan_payload_async") as task:
        mw(_post(rf, membership.user, json.dumps({"email": "a@b.com"})))
    assert task.delay.call_count >= 1
    kwargs = task.delay.call_args_list[0].kwargs
    assert kwargs["tenant_id"] == membership.tenant.pk
    assert kwargs["direction"] == "inbound"
    assert kwargs["endpoint"] == "/api/x/"


def test_task_run_persists_presidio_events(membership):
    from wiregraph_apps.detection import tasks
    from wiregraph_apps.detection.models import DataEvent

    fake_matches = [Match("person_name", 0, 8, "Jane Doe", 0.85)]

    with override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": True}):
        with patch(
            "wiregraph_apps.detection.presidio_scanner.PresidioScanner.scan",
            return_value=fake_matches,
        ):
            result = tasks._run(
                tenant_id=membership.tenant.pk,
                text="Jane Doe was here",
                direction="inbound",
                endpoint="/api/x/",
                method="POST",
                request_id="req-1",
            )

    assert result == {"persisted": 1}
    event = DataEvent.objects.get(detection_method="presidio")
    assert event.data_asset.name == "person_name"
    assert event.tenant_id == membership.tenant.pk


def test_task_run_skips_when_disabled(membership):
    from wiregraph_apps.detection import tasks

    with override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": False}):
        result = tasks._run(
            tenant_id=membership.tenant.pk,
            text="x",
            direction="inbound",
            endpoint="/x",
            method="GET",
            request_id="",
        )
    assert result == {"skipped": "ENABLE_PRESIDIO is False"}


def test_task_run_dedupes_against_regex(membership):
    from wiregraph_apps.detection import tasks
    from wiregraph_apps.detection.models import DataEvent

    with override_settings(WIREGRAPH={"ENABLED": True, "ENABLE_PRESIDIO": True}):
        with patch(
            "wiregraph_apps.detection.presidio_scanner.PresidioScanner.scan",
            return_value=[Match("email", 0, 16, "jane@example.com", 0.85)],
        ):
            result = tasks._run(
                tenant_id=membership.tenant.pk,
                text="jane@example.com",
                direction="inbound",
                endpoint="/x",
                method="POST",
                request_id="",
            )

    assert result == {"persisted": 0}
    assert not DataEvent.objects.filter(detection_method="presidio").exists()
