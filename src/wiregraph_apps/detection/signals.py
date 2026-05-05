"""Public signal contract for the detection pipeline.

Each ``Signal`` below is part of the library's public surface — external
consumers connect receivers to react to detection events. Renaming or
changing payload kwargs is a breaking change.

Payloads are documented as ``@dataclass`` types. Django's ``Signal`` does
not enforce kwargs at dispatch time, so the dataclasses are a contract
artifact (introspectable via each signal's ``payload_class`` attribute),
not runtime validation. Producers must send all fields listed on the
matching dataclass; consumers can rely on every field being present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from django.dispatch import Signal


@dataclass(frozen=True)
class PIIDetectedPayload:
    """Payload for :data:`pii_detected`.

    Attributes:
        data_event: The persisted ``DataEvent`` row. Already classified
            (``outcome`` and ``decision_reason`` populated).
        request: The originating ``HttpRequest`` for inbound paths, or
            ``None`` when fired from a non-request context (e.g. async
            Presidio task or egress interceptor).
    """

    data_event: Any
    request: Optional[Any]


@dataclass(frozen=True)
class NewDataAssetDiscoveredPayload:
    """Payload for :data:`new_data_asset_discovered`.

    Attributes:
        data_asset: The newly created ``DataAsset`` row for this tenant.
        tenant: The owning ``Tenant``.
    """

    data_asset: Any
    tenant: Any


@dataclass(frozen=True)
class EventClassifiedPayload:
    """Payload for :data:`event_classified`.

    Attributes:
        data_event: The persisted ``DataEvent`` row, with ``outcome``
            and ``decision_reason`` set.
        external_service: The matched ``ExternalService`` row, or
            ``None`` for inbound paths with no resolvable sink.
        effective_level: Outcome gated by detector confidence — one of
            ``"expected"``, ``"acceptable"``, ``"suspicious"``,
            ``"prohibited"`` (see ``classifier.effective_alert_level``).
            Receivers should branch on this rather than on ``outcome``.
        confidence: Detector confidence in ``[0.0, 1.0]``.
        reason: Human-readable classifier reason string (may be empty).
    """

    data_event: Any
    external_service: Optional[Any]
    effective_level: str
    confidence: float
    reason: str


pii_detected = Signal()
"""Fired after a ``DataEvent`` is persisted on either inbound or async paths.

Producer: :func:`wiregraph_apps.detection.persistence.persist_matches` (called
from request/response middleware and the Presidio Celery task). Not fired by
the egress interceptor — egress consumers should listen to
:data:`event_classified` or :data:`wiregraph_apps.egress.signals.egress_pii_leak`.

Receivers: none built-in. Consumer-facing extension point.

Payload: see :class:`PIIDetectedPayload`.
"""
pii_detected.payload_class = PIIDetectedPayload


new_data_asset_discovered = Signal()
"""Fired the first time a given ``DataAsset.name`` is seen for a tenant.

Producer: :func:`wiregraph_apps.detection.persistence.persist_matches` and
:func:`wiregraph_apps.detection.persistence.persist_egress_matches`, after
the ``DataAsset`` row is created.

Receivers: :func:`wiregraph_apps.detection.receivers.alert_on_new_asset`
posts a Slack notification via the configured ``ALERT_WEBHOOK_URL``.

Payload: see :class:`NewDataAssetDiscoveredPayload`.
"""
new_data_asset_discovered.payload_class = NewDataAssetDiscoveredPayload


event_classified = Signal()
"""Fired after classification runs on a ``DataEvent`` (inbound and egress).

This is the canonical alert-routing signal — it carries the
confidence-gated ``effective_level`` so receivers don't have to recompute
it. Producers also fire :data:`pii_detected` (inbound) or
:data:`wiregraph_apps.egress.signals.egress_pii_leak` (egress, prohibited
only) for backwards compatibility, but new consumers should prefer this.

Producer: both ``persist_matches`` and ``persist_egress_matches`` in
:mod:`wiregraph_apps.detection.persistence`.

Receivers: :func:`wiregraph_apps.detection.receivers.route_classified_event`
dispatches Slack/pager alerts (with dedup) for ``prohibited`` and
``suspicious``, records ``acceptable`` to the daily digest, and no-ops on
``expected``.

Payload: see :class:`EventClassifiedPayload`.
"""
event_classified.payload_class = EventClassifiedPayload
