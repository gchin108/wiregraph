from datetime import timedelta

import pytest
from django.utils import timezone

from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.reporting.purge import purge_expired_events
from tests.fixtures.factories import DataEventFactory

pytestmark = pytest.mark.django_db


def _event(days_old: int):
    return DataEventFactory(timestamp=timezone.now() - timedelta(days=days_old))


def test_purge_deletes_events_older_than_retention(settings):
    settings.WIREGRAPH = {"DATA_RETENTION_DAYS": 30}
    _event(days_old=40)  # expired
    _event(days_old=35)  # expired
    kept = _event(days_old=10)  # fresh

    result = purge_expired_events()

    assert result.candidates == 2
    assert result.deleted == 2
    assert DataEvent.objects.filter(pk=kept.pk).exists()
    assert DataEvent.objects.count() == 1


def test_purge_dry_run_deletes_nothing(settings):
    settings.WIREGRAPH = {"DATA_RETENTION_DAYS": 7}
    _event(days_old=30)
    _event(days_old=20)

    result = purge_expired_events(dry_run=True)

    assert result.dry_run is True
    assert result.candidates == 2
    assert result.deleted == 0
    assert DataEvent.objects.count() == 2


def test_purge_respects_retention_days_override(settings):
    settings.WIREGRAPH = {"DATA_RETENTION_DAYS": 90}
    _event(days_old=10)

    # Explicit override: retain only 5 days → the 10-day-old event expires.
    result = purge_expired_events(retention_days=5)

    assert result.deleted == 1


def test_purge_batches_in_chunks(settings):
    settings.WIREGRAPH = {"DATA_RETENTION_DAYS": 30}
    for _ in range(5):
        _event(days_old=40)

    result = purge_expired_events(batch_size=2)

    assert result.deleted == 5
    assert DataEvent.objects.count() == 0


def test_purge_nothing_to_delete(settings):
    settings.WIREGRAPH = {"DATA_RETENTION_DAYS": 30}
    _event(days_old=5)

    result = purge_expired_events()

    assert result.candidates == 0
    assert result.deleted == 0
