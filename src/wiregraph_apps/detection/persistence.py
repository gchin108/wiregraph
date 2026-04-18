"""Shared persistence for detection matches.

Used by both the sync middleware (regex) and the async Celery task (Presidio)
so the ``DataEvent`` shape, allowlist filtering, and signal dispatch stay in
one place.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from wiregraph_apps.detection.allowlist import filter_matches
from wiregraph_apps.detection.models import DataAsset, DataEvent
from wiregraph_apps.detection.regex_scanner import Match, redact
from wiregraph_apps.detection.signals import new_data_asset_discovered, pii_detected

logger = logging.getLogger(__name__)


def persist_matches(
    *,
    tenant,
    matches: Iterable[Match],
    direction: str,
    endpoint: str,
    method: str,
    detection_method: str,
    request_id: str = "",
    request=None,
) -> list[DataEvent]:
    """Filter, coalesce, and persist matches. Returns the created ``DataEvent`` rows."""
    filtered = filter_matches(tenant, list(matches), endpoint)
    if not filtered:
        return []

    coalesced: dict[str, list[Match]] = {}
    for match in filtered:
        coalesced.setdefault(match.asset_name, []).append(match)

    new_assets: list[DataAsset] = []
    events: list[DataEvent] = []
    now = timezone.now()

    with transaction.atomic():
        for asset_name, asset_matches in coalesced.items():
            asset, created = DataAsset.objects.get_or_create(
                tenant=tenant,
                name=asset_name,
                defaults={"label": asset_name.replace("_", " ").title()},
            )
            if created:
                new_assets.append(asset)
            first = asset_matches[0]
            events.append(
                DataEvent(
                    tenant=tenant,
                    data_asset=asset,
                    direction=direction,
                    endpoint=endpoint,
                    method=method,
                    detection_method=detection_method,
                    redacted_snippet=redact(first.value),
                    confidence=first.confidence,
                    request_id=request_id,
                    timestamp=now,
                    match_count=len(asset_matches),
                )
            )
        created_events = DataEvent.objects.bulk_create(events)

    for asset in new_assets:
        new_data_asset_discovered.send(
            sender=DataAsset,
            data_asset=asset,
            tenant=tenant,
        )
    for event in created_events:
        pii_detected.send(
            sender=DataEvent,
            data_event=event,
            request=request,
        )
    return created_events
