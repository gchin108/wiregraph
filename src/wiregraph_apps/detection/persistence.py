"""Shared persistence for detection matches.

The single home for all ``DataEvent`` and detection-rollup writes. Inbound and
outbound (regex) middleware, the async Presidio task, and the egress
interceptor all funnel through this module so the row shape, allowlist
filtering, classification, and signal dispatch stay in one place.

Public surface:
    * :func:`persist_matches` — bulk path used by middleware/tasks.
      Coalesces matches by asset (one row per ``(asset, request)``).
    * :func:`persist_egress_matches` — per-match path used by the egress
      interceptor. Preserves ``json_path`` per match and fires
      ``egress_pii_leak`` on prohibited.
    * :func:`update_shadow_counter` — daily ``ShadowDecisionCounter`` rollup.
    * :func:`record_escalation` — daily ``EscalationCounter`` rollup.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from wiregraph_apps.detection.adapters.allowlist import filter_matches
from wiregraph_apps.detection.adapters.classifier import (
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
from wiregraph_apps.detection.adapters.sinks import sensitivity_for

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
    """Filter, coalesce by asset, and persist matches. Returns the created rows."""
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
        _fire_post_persist_signals(event, request=request, external_service=external_service)
    return created_events


def persist_egress_matches(
    *,
    tenant,
    matches: Iterable[Match],
    external_service,
    endpoint: str,
    method: str,
    request_id: str = "",
    now=None,
) -> list[DataEvent]:
    """Per-match egress path. Creates one ``DataEvent`` per match (preserving
    ``json_path``), classifies, fires ``egress_pii_leak`` on prohibited.

    Caller (egress interceptor) is responsible for ``ExternalService``
    upsert and for running ``filter_matches`` if it has already done so;
    we re-filter defensively so this entry point is safe to call directly.
    """
    from wiregraph_apps.egress.signals import egress_pii_leak

    host = external_service.domain if external_service is not None else ""
    filtered = filter_matches(tenant, list(matches), endpoint, host)
    if not filtered:
        return []

    if now is None:
        now = timezone.now()

    asset_cache: dict[str, DataAsset] = {}
    new_assets: list[DataAsset] = []
    created_events: list[DataEvent] = []

    with transaction.atomic():
        for match in filtered:
            asset = asset_cache.get(match.asset_name)
            if asset is None:
                asset, created = DataAsset.objects.get_or_create(
                    tenant=tenant,
                    name=match.asset_name,
                    defaults={
                        "label": match.asset_name.replace("_", " ").title(),
                        "sensitivity_level": sensitivity_for(match.asset_name),
                    },
                )
                asset_cache[match.asset_name] = asset
                if created:
                    new_assets.append(asset)
            event = DataEvent.objects.create(
                tenant=tenant,
                data_asset=asset,
                external_service=external_service,
                direction="egress",
                endpoint=endpoint,
                method=method,
                detection_method="regex",
                redacted_snippet=redact(match.value),
                confidence=match.confidence,
                json_path=match.json_path or "",
                request_id=request_id,
                timestamp=now,
            )
            try:
                outcome, reason = classify_for_event(tenant, event, external_service)
                event.outcome = outcome
                event.decision_reason = reason
                try:
                    apply_shadow_decision(event)
                except Exception:
                    logger.exception("wiregraph: shadow decision failed")
                DataEvent.objects.filter(pk=event.pk).update(
                    outcome=outcome,
                    decision_reason=reason,
                    shadow_alert_level=event.shadow_alert_level,
                )
            except Exception:
                logger.exception("wiregraph: classifier failed on egress event")
            created_events.append(event)

    for asset in new_assets:
        new_data_asset_discovered.send(
            sender=DataAsset,
            data_asset=asset,
            tenant=tenant,
        )
    for event in created_events:
        level = _safe_effective_level(event)
        if level == "prohibited":
            egress_pii_leak.send(
                sender=DataEvent,
                data_event=event,
                external_service=external_service,
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


def update_shadow_counter(event, level: str) -> None:
    """Upsert today's ``ShadowDecisionCounter`` row. Best-effort."""
    from django.db.models import F

    from wiregraph_apps.reporting.models import ShadowDecisionCounter

    day = event.timestamp.date() if getattr(event, "timestamp", None) else None
    tenant_id = getattr(event, "tenant_id", None)
    if day is None or tenant_id is None:
        return

    obj, created = ShadowDecisionCounter.objects.get_or_create(
        tenant_id=tenant_id,
        day=day,
        outcome=event.outcome,
        shadow_alert_level=level,
        defaults={"count": 1},
    )
    if not created:
        ShadowDecisionCounter.objects.filter(pk=obj.pk).update(count=F("count") + 1)


def record_escalation(tenant_id) -> None:
    """Upsert today's ``EscalationCounter`` row. Best-effort."""
    from django.db.models import F

    from wiregraph_apps.reporting.models import EscalationCounter

    if tenant_id is None:
        return
    day = timezone.now().date()
    try:
        obj, created = EscalationCounter.objects.get_or_create(
            tenant_id=tenant_id,
            day=day,
            defaults={"count": 1},
        )
        if not created:
            EscalationCounter.objects.filter(pk=obj.pk).update(count=F("count") + 1)
    except Exception:
        logger.exception("wiregraph: escalation rollup upsert failed")


def _fire_post_persist_signals(event, *, request, external_service) -> None:
    level = _safe_effective_level(event)
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


def _safe_effective_level(event) -> str:
    try:
        return effective_alert_level(
            event.outcome or "", float(event.confidence or 0.0)
        )
    except Exception:
        logger.exception("wiregraph: effective_alert_level failed")
        return event.outcome or ""
