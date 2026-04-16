"""Shared purge logic for ``DataEvent`` retention.

Used by both the ``wiregraph_purge`` management command and the optional
Celery task (``wiregraph.celery.purge_expired_events``). Deletion is done in
batches of primary keys so we don't load the full matching queryset into
memory and so the DB sees a bounded transaction footprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from core_apps.common.conf import get_config

DEFAULT_BATCH_SIZE = 1000


@dataclass(frozen=True)
class PurgeResult:
    cutoff_iso: str
    candidates: int
    deleted: int
    dry_run: bool


def purge_expired_events(
    *,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    retention_days: int | None = None,
) -> PurgeResult:
    from core_apps.detection.models import DataEvent

    if retention_days is None:
        retention_days = int(get_config("DATA_RETENTION_DAYS"))

    cutoff = timezone.now() - timedelta(days=retention_days)
    candidates_qs = DataEvent.objects.filter(timestamp__lt=cutoff)
    candidates = candidates_qs.count()

    if dry_run or candidates == 0:
        return PurgeResult(
            cutoff_iso=cutoff.isoformat(),
            candidates=candidates,
            deleted=0,
            dry_run=dry_run,
        )

    deleted_total = 0
    while True:
        batch_ids = list(
            DataEvent.objects.filter(timestamp__lt=cutoff)
            .values_list("pk", flat=True)[:batch_size]
        )
        if not batch_ids:
            break
        deleted_count, _ = DataEvent.objects.filter(pk__in=batch_ids).delete()
        deleted_total += deleted_count

    return PurgeResult(
        cutoff_iso=cutoff.isoformat(),
        candidates=candidates,
        deleted=deleted_total,
        dry_run=False,
    )
