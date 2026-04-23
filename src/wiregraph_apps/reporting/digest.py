"""Digest upsert helper for ``acceptable`` classification outcomes (§5)."""

from __future__ import annotations

import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


def record_digest_entry(event, external_service) -> None:
    """Upsert today's digest row for the event. Best-effort."""
    from wiregraph_apps.reporting.models import AlertDigestEntry

    tenant_id = getattr(event, "tenant_id", None)
    if tenant_id is None:
        return
    asset = getattr(event, "data_asset", None)
    asset_name = getattr(asset, "name", "") if asset is not None else ""
    domain = getattr(external_service, "domain", "") if external_service else ""
    now = timezone.now()
    day = now.date()
    try:
        obj, created = AlertDigestEntry.objects.get_or_create(
            tenant_id=tenant_id,
            day=day,
            outcome=event.outcome or "",
            asset_name=asset_name,
            service_domain=domain,
            defaults={"count": 1, "first_seen_at": now, "last_seen_at": now},
        )
        if not created:
            AlertDigestEntry.objects.filter(pk=obj.pk).update(
                count=F("count") + 1,
                last_seen_at=now,
            )
    except Exception:
        logger.exception("wiregraph: digest upsert failed")
