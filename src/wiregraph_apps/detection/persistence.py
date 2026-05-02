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
from wiregraph_apps.detection.classifier_django import (
    apply_shadow_decision,
    classify_for_event,
    effective_alert_level,
)
from wiregraph_apps.detection.models import DataAsset, DataEvent
from wiregraph_apps.detection.regex_scanner import Match, redact
from wiregraph_apps.detection.signals import (
    event_classified,
    new_data_asset_discovered,
    pii_detected,
)
from wiregraph_apps.sinks import sensitivity_for

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
    external_service=None,
) -> list[DataEvent]:
    """Filter, coalesce, and persist matches. Returns the created ``DataEvent`` rows."""
    host = external_service.domain if external_service is not None else ""
    filtered = filter_matches(tenant, list(matches), endpoint, host)
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
                defaults={
                    "label": asset_name.replace("_", " ").title(),
                    "sensitivity_level": sensitivity_for(asset_name),
                },
            )
            if created:
                new_assets.append(asset)
            first = asset_matches[0]
            events.append(
                DataEvent(
                    tenant=tenant,
                    data_asset=asset,
                    external_service=external_service,
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

        for event in created_events:
            try:
                outcome, reason = classify_for_event(tenant, event, external_service)
            except Exception:
                logger.exception("wiregraph: classifier failed; leaving defaults")
                continue
            event.outcome = outcome
            event.decision_reason = reason
            try:
                apply_shadow_decision(event)
            except Exception:
                logger.exception("wiregraph: shadow decision failed")
        DataEvent.objects.bulk_update(
            created_events, ["outcome", "decision_reason", "shadow_alert_level"]
        )

    for asset in new_assets:
        new_data_asset_discovered.send(
            sender=DataAsset,
            data_asset=asset,
            tenant=tenant,
        )
    for event in created_events:
        try:
            level = effective_alert_level(
                event.outcome or "", float(event.confidence or 0.0)
            )
        except Exception:
            logger.exception("wiregraph: effective_alert_level failed")
            level = event.outcome or ""

        # pii_detected is an audit signal — "PII was observed" — and fires on
        # every detection so subscribers can log/track regardless of outcome.
        pii_detected.send(
            sender=DataEvent,
            data_event=event,
            request=request,
        )
        try:
            event_classified.send(
                sender=DataEvent,
                data_event=event,
                external_service=external_service,
                effective_level=level,
                confidence=float(event.confidence or 0.0),
                reason=event.decision_reason or "",
            )
        except Exception:
            logger.exception("wiregraph: event_classified dispatch failed")
    return created_events
