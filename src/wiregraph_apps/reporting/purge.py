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

from wiregraph_apps.common.conf import get_config, get_expected_retention_days

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
    expected_retention_days: int | None = None,
) -> PurgeResult:
    """Purge expired ``DataEvent`` rows.

    Runs two sweeps with separate retention windows:

    * ``outcome="expected"`` rows older than ``expected_retention_days``
      (default ``WIREGRAPH["RETENTION_DAYS_EXPECTED"]``).
    * All other rows older than ``retention_days``
      (default ``WIREGRAPH["DATA_RETENTION_DAYS"]``).

    The returned ``cutoff_iso`` reflects the longer (non-expected) window for
    backward compatibility; ``candidates`` and ``deleted`` aggregate both
    sweeps.
    """
    from wiregraph_apps.detection.models import DataEvent

    if retention_days is None:
        retention_days = int(get_config("DATA_RETENTION_DAYS"))
    if expected_retention_days is None:
        # Expected retention is the shorter of the configured value and the
        # main retention. Keeps explicit ``--retention-days N`` overrides
        # intuitive: they purge *everything* older than N, not just
        # non-expected.
        expected_retention_days = min(
            get_expected_retention_days(), retention_days
        )

    now = timezone.now()
    cutoff = now - timedelta(days=retention_days)
    expected_cutoff = now - timedelta(days=expected_retention_days)

    main_qs = DataEvent.objects.filter(timestamp__lt=cutoff).exclude(
        outcome="expected"
    )
    expected_qs = DataEvent.objects.filter(
        timestamp__lt=expected_cutoff, outcome="expected"
    )
    candidates = main_qs.count() + expected_qs.count()

    if dry_run or candidates == 0:
        return PurgeResult(
            cutoff_iso=cutoff.isoformat(),
            candidates=candidates,
            deleted=0,
            dry_run=dry_run,
        )

    deleted_total = 0
    for filter_kwargs in (
        {"timestamp__lt": expected_cutoff, "outcome": "expected"},
        # main sweep: exclude expected via a second filter call below
        {"timestamp__lt": cutoff},
    ):
        while True:
            qs = DataEvent.objects.filter(**filter_kwargs)
            if "outcome" not in filter_kwargs:
                qs = qs.exclude(outcome="expected")
            batch_ids = list(qs.values_list("pk", flat=True)[:batch_size])
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
