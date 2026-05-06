"""Persistence layer must write DataEvents without DRF on the import path."""

from __future__ import annotations

import pytest

from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.detection.persistence import persist_matches
from wiregraph_apps.detection.regex_scanner import Match
from tests.fixtures.factories import TenantFactory


pytestmark = pytest.mark.django_db


def test_persist_matches_writes_event_with_drf_hidden(no_drf):
    tenant = TenantFactory()
    matches = [
        Match(
            asset_name="email",
            start=0,
            end=18,
            value="leaked@example.com",
            confidence=0.99,
            json_path="$.user.email",
        )
    ]

    events = persist_matches(
        tenant=tenant,
        matches=matches,
        direction="inbound",
        endpoint="/some/endpoint",
        method="POST",
        detection_method="regex",
        request_id="req-abc",
    )

    assert len(events) == 1
    assert DataEvent.objects.filter(tenant=tenant, data_asset__name="email").exists()
