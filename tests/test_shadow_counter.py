"""DB-backed tests for the ShadowDecisionCounter rollup."""

import pytest
from django.test import override_settings

from tests.fixtures.factories import DataEventFactory
from wiregraph_apps.detection.classifier import apply_shadow_decision
from wiregraph_apps.reporting.models import ShadowDecisionCounter

pytestmark = pytest.mark.django_db


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_counter_created_on_first_event():
    event = DataEventFactory(outcome="prohibited", confidence=0.95)
    apply_shadow_decision(event)

    row = ShadowDecisionCounter.objects.get(
        tenant=event.tenant,
        day=event.timestamp.date(),
        outcome="prohibited",
        shadow_alert_level="prohibited",
    )
    assert row.count == 1


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_counter_increments_on_repeat_event():
    e1 = DataEventFactory(outcome="suspicious", confidence=0.95)
    e2 = DataEventFactory(
        tenant=e1.tenant,
        data_asset=e1.data_asset,
        outcome="suspicious",
        confidence=0.95,
        timestamp=e1.timestamp,
    )

    apply_shadow_decision(e1)
    apply_shadow_decision(e2)

    row = ShadowDecisionCounter.objects.get(
        tenant=e1.tenant, day=e1.timestamp.date(), outcome="suspicious", shadow_alert_level="suspicious"
    )
    assert row.count == 2


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_counter_buckets_by_shadow_level():
    # Same outcome, different confidence → different shadow buckets.
    high = DataEventFactory(outcome="prohibited", confidence=0.95)
    low = DataEventFactory(
        tenant=high.tenant,
        outcome="prohibited",
        confidence=0.2,
        timestamp=high.timestamp,
    )
    apply_shadow_decision(high)
    apply_shadow_decision(low)

    rows = {
        r.shadow_alert_level: r.count
        for r in ShadowDecisionCounter.objects.filter(tenant=high.tenant)
    }
    assert rows == {"prohibited": 1, "suspicious": 1}


@override_settings(WIREGRAPH={"SHADOW_MODE": False})
def test_counter_not_written_when_shadow_disabled():
    event = DataEventFactory(outcome="prohibited", confidence=0.95)
    apply_shadow_decision(event)
    assert not ShadowDecisionCounter.objects.exists()
