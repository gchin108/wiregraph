"""Django wrapper around :mod:`wiregraph_core.classifier`.

Resolves ORM rows into the pure-core dataclasses, calls the deterministic
classifier, then performs Django-only side effects (history queries, shadow
counter writes, structured logging).
"""

from __future__ import annotations

import logging

from wiregraph_apps.common.conf import (
    get_confidence_thresholds,
    get_llm_policy,
    is_shadow_mode,
)
from wiregraph_apps.detection.allowlist import find_matching_rule
from wiregraph_core.classifier import (
    classify as _pure_classify,
    effective_alert_level as _pure_effective_alert_level,
)
from wiregraph_core.types import (
    AlertLevel,
    Asset,
    FlowHistory,
    Outcome,
    Policy,
    RuleHit,
    Sink,
)

_shadow_logger = logging.getLogger("wiregraph.shadow")


def check_is_new_flow(tenant, data_asset, external_service) -> bool:
    """First sight of the ``(tenant, asset, service)`` triple?"""
    from wiregraph_apps.detection.models import DataEvent

    if external_service is None:
        return False
    return not DataEvent.objects.filter(
        tenant=tenant,
        data_asset=data_asset,
        external_service=external_service,
    ).exists()


def classify_for_event(tenant, data_event, external_service) -> tuple[Outcome, str]:
    """Resolve ORM rows → pure :func:`classify` → ``(outcome, reason)`` tuple.

    Callers pass the freshly persisted ``data_event`` so new-flow detection
    can ``exists()``-check past events with the new event's own row excluded
    by PK.
    """
    from wiregraph_apps.detection.models import DataEvent

    asset = data_event.data_asset
    host = external_service.domain if external_service is not None else ""

    if external_service is not None:
        sink = Sink(
            domain=external_service.domain,
            category=external_service.category or "unknown",
            trust_tier=external_service.trust_tier or "unknown",
            accepts_assets=list(external_service.accepts_assets or []),
        )
    else:
        sink = Sink(
            domain="",
            category="internal",
            trust_tier="trusted",
            accepts_assets=["*"],
        )

    rule = find_matching_rule(tenant, asset.name, data_event.endpoint, host)
    rule_hit = RuleHit() if rule is not None else None

    is_new = False
    if external_service is not None:
        is_new = (
            not DataEvent.objects.filter(
                tenant=tenant,
                data_asset=asset,
                external_service=external_service,
            )
            .exclude(pk=data_event.pk)
            .exists()
        )

    asset_spec = Asset(
        name=asset.name,
        sensitivity_level=asset.sensitivity_level or "medium",
    )
    policy = Policy(llm_mode=get_llm_policy())
    history = FlowHistory(is_new_flow=is_new)

    decision = _pure_classify(asset_spec, sink, rule_hit, policy, history)
    return decision.outcome, decision.reason


def effective_alert_level(
    outcome: Outcome,
    confidence: float,
    thresholds: tuple[float, float] | None = None,
) -> AlertLevel:
    """Settings-aware wrapper around :func:`wiregraph_core.classifier.effective_alert_level`."""
    if thresholds is None:
        thresholds = get_confidence_thresholds()
    return _pure_effective_alert_level(outcome, confidence, thresholds)


def _increment_shadow_counter(event, level: str) -> None:
    """Upsert the daily rollup row. Best-effort — failures are swallowed."""
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


def apply_shadow_decision(event) -> str:
    """Shadow-mode side effects for a classified event (proposal §9.2).

    Computes ``effective_alert_level`` from the event's stored outcome/confidence,
    sets ``event.shadow_alert_level`` in-memory, emits a structured log line,
    and upserts the daily rollup. No-op when ``SHADOW_MODE`` is off. Returns
    the computed level (or ``""`` if disabled).
    """
    if not is_shadow_mode():
        return ""

    level = effective_alert_level(event.outcome, event.confidence)
    event.shadow_alert_level = level

    service = getattr(event, "external_service", None)
    asset = getattr(event, "data_asset", None)
    _shadow_logger.info(
        "wiregraph.shadow event_id=%s tenant=%s outcome=%s level=%s "
        "confidence=%.3f reason=%s asset=%s service=%s",
        getattr(event, "pk", None),
        getattr(event, "tenant_id", None),
        event.outcome,
        level,
        float(event.confidence or 0.0),
        event.decision_reason or "",
        getattr(asset, "name", "") if asset is not None else "",
        getattr(service, "domain", "") if service is not None else "",
    )

    try:
        _increment_shadow_counter(event, level)
    except Exception:
        _shadow_logger.exception("wiregraph: shadow counter increment failed")

    return level
