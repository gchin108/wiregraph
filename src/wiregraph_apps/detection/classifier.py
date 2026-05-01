"""Deterministic classifier for (asset, sink) flows.

This is a **pure function**: no DB access, no Django imports. Callers are
responsible for resolving their models into the dataclass specs below and
then invoking :func:`classify`. That keeps the decision logic trivially unit
testable and matches the "Testability contract" in the proposal (§3).

Classification is **deterministic** on its inputs. Detector confidence is not
an input here — confidence gates *alerting*, not *classification* (proposal
§4, not implemented in Phase 1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from wiregraph_apps.sinks import CATEGORY_DEFAULTS

_shadow_logger = logging.getLogger("wiregraph.shadow")


@dataclass(frozen=True)
class AssetSpec:
    name: str
    sensitivity_level: str  # "low" | "medium" | "high" | "critical"


@dataclass(frozen=True)
class ServiceSpec:
    domain: str
    category: str       # e.g. "llm", "payments", "unknown"
    trust_tier: str     # "trusted" | "known" | "unknown"
    accepts_assets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleHit:
    """An AllowlistRule matched — classification short-circuits to expected."""


@dataclass(frozen=True)
class Policy:
    llm_mode: str = "strict"  # "strict" | "relaxed"


Outcome = str  # "expected" | "acceptable" | "suspicious" | "prohibited"


def effective_accepts(service: ServiceSpec) -> list[str]:
    """Return the effective accept-list for a service.

    Per-domain ``accepts_assets`` overrides category default; an empty explicit
    list still means "use category default" (proposal §2, footnote).
    """
    if service.accepts_assets:
        return list(service.accepts_assets)
    return list(CATEGORY_DEFAULTS.get(service.category, []))


def classify(
    asset: AssetSpec,
    service: ServiceSpec,
    rule_hit: RuleHit | None,
    policy: Policy,
    is_new_flow: bool = False,
) -> tuple[Outcome, str]:
    """Return ``(outcome, decision_reason)`` for a single (asset, service) flow.

    ``decision_reason`` is a ``namespace:detail`` string — see
    ``constants.REASON_PREFIXES``.
    """
    if rule_hit is not None:
        return "expected", "rule:allowlist"

    accepts = effective_accepts(service)
    if "*" in accepts or asset.name in accepts:
        return "expected", f"category:{service.category}_accepts_{asset.name}"

    if service.category == "llm":
        if policy.llm_mode == "strict" and asset.sensitivity_level in {
            "medium",
            "high",
            "critical",
        }:
            return "prohibited", "policy:pii_to_llm"
        if policy.llm_mode == "relaxed" and asset.sensitivity_level in {
            "high",
            "critical",
        }:
            return "prohibited", "policy:sensitive_to_llm"
        # relaxed mode + medium asset → fall through

    if service.category == "unknown" and asset.sensitivity_level in {
        "high",
        "critical",
    }:
        return "prohibited", "policy:sensitive_to_unknown_sink"

    if is_new_flow:
        return "suspicious", "flow:new_data_flow"

    if service.trust_tier == "trusted":
        return "acceptable", f"trust:trusted_sink_category_{service.category}"

    if asset.sensitivity_level == "low":
        return "acceptable", "sensitivity:low"

    # Known sink receiving an asset outside its category expectations.
    return "suspicious", f"category:{service.category}_unexpected_{asset.name}"


def classify_for_event(tenant, data_event, external_service) -> tuple[Outcome, str]:
    """Model-aware wrapper: resolve DB objects into specs, call :func:`classify`.

    Callers pass the freshly persisted ``data_event`` so new-flow detection
    can ``exists()``-check past events (the new event's own row is excluded
    by PK). Kept out of :func:`classify` to preserve its purity.
    """
    from wiregraph_apps.common.conf import get_llm_policy
    from wiregraph_apps.detection.allowlist import find_matching_rule
    from wiregraph_apps.detection.models import DataEvent

    asset = data_event.data_asset
    host = external_service.domain if external_service is not None else ""

    if external_service is not None:
        service_spec = ServiceSpec(
            domain=external_service.domain,
            category=external_service.category or "unknown",
            trust_tier=external_service.trust_tier or "unknown",
            accepts_assets=list(external_service.accepts_assets or []),
        )
    else:
        # Inbound / outbound (no external sink) — treat as internal.
        service_spec = ServiceSpec(
            domain="",
            category="internal",
            trust_tier="trusted",
            accepts_assets=["*"],
        )

    rule = find_matching_rule(tenant, asset.name, data_event.endpoint, host)
    rule_hit = RuleHit() if rule is not None else None

    is_new = False
    if external_service is not None:
        # when no prior event exists, return early with "suspicious", "flow:new_data_flow" before it reaches the sensitivity check.
        is_new = not DataEvent.objects.filter(
            tenant=tenant,
            data_asset=asset,
            external_service=external_service,
        ).exclude(pk=data_event.pk).exists()

    asset_spec = AssetSpec(
        name=asset.name,
        sensitivity_level=asset.sensitivity_level or "medium",
    )
    policy = Policy(llm_mode=get_llm_policy())

    return classify(asset_spec, service_spec, rule_hit, policy, is_new_flow=is_new)


AlertLevel = str  # "prohibited" | "suspicious" | "acceptable" | "expected"


def effective_alert_level(
    outcome: Outcome,
    confidence: float,
    thresholds: tuple[float, float] | None = None,
) -> AlertLevel:
    """Map a classification outcome to the level receivers would dispatch on.

    Classification is deterministic; this is where detector confidence gates
    whether a given outcome escalates to a human (proposal §4).

    - Below ``low`` threshold: downgrade noisy matches — ``suspicious`` →
      ``acceptable``, ``prohibited`` → ``suspicious``.
    - At/above ``high`` threshold: no downgrades (future hook for escalation).
    - ``expected`` and ``acceptable`` are never escalated by confidence alone.
    """
    if thresholds is None:
        from wiregraph_apps.common.conf import get_confidence_thresholds
        thresholds = get_confidence_thresholds()
    low, _high = thresholds

    if confidence < low:
        if outcome == "suspicious":
            return "acceptable"
        if outcome == "prohibited":
            return "suspicious"
    return outcome


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
    sets ``event.shadow_alert_level`` in-memory, and emits a structured log line.
    Caller is responsible for persisting the field. No-op when ``SHADOW_MODE`` is
    off. Returns the computed level (or ``""`` if disabled).
    """
    from wiregraph_apps.common.conf import is_shadow_mode

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


def check_is_new_flow(tenant, data_asset, external_service) -> bool:
    """DB-backed helper — first sight of ``(tenant, asset, service)`` triple.

    Cheap ``exists()`` on DataEvent. Kept out of :func:`classify` to preserve
    its purity; call sites pass the boolean in.
    """
    from wiregraph_apps.detection.models import DataEvent

    if external_service is None:
        return False
    return not DataEvent.objects.filter(
        tenant=tenant,
        data_asset=data_asset,
        external_service=external_service,
    ).exists()
