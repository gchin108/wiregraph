"""Read-side aggregations for the dashboard.

Endpoint nodes group ``DataEvent`` rows by ``(external_service, endpoint, method)``
and surface the stats the dashboard card needs: worst outcome seen, per-asset
match counts, last-seen timestamp, and an hourly-bucket sparkline.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db.models import Count, Max, Min, QuerySet
from django.db.models.functions import TruncHour

from wiregraph_apps.detection.models import DataAsset, DataEvent

OUTCOME_RANK = {"expected": 0, "acceptable": 1, "suspicious": 2, "prohibited": 3}
SPARKLINE_WINDOW = timedelta(days=7)
# All direction strings that represent traffic leaving the app. The interceptor
# writes "egress" today; older rows and seed data carry "wiregraph_egress" or
# "outbound". Treat all three as outbound for endpoint-node aggregation.
OUTBOUND_DIRECTIONS = ("outbound", "wiregraph_egress", "egress")


@dataclass
class AssetCount:
    name: str
    label: str
    count: int


@dataclass
class HourBucket:
    hour: datetime
    count: int


@dataclass
class EndpointNode:
    id: str
    external_service_id: str | int | None
    external_service_name: str | None
    external_service_domain: str | None
    endpoint: str
    method: str
    direction: str
    worst_outcome: str
    event_count: int
    last_seen: datetime
    first_seen: datetime
    assets: list[AssetCount] = field(default_factory=list)
    sparkline: list[HourBucket] = field(default_factory=list)


def _encode_id(external_service_id, endpoint: str, method: str) -> str:
    raw = f"{external_service_id or ''}|{method}|{endpoint}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_endpoint_id(node_id: str) -> tuple[str | None, str, str]:
    """Return (external_service_id, endpoint, method) — id is the raw PK string."""

    padding = "=" * (-len(node_id) % 4)
    try:
        raw = base64.urlsafe_b64decode(node_id + padding).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Invalid endpoint node id") from exc
    svc, method, endpoint = raw.split("|", 2)
    return (svc or None), endpoint, method


def _outbound_events(tenant) -> QuerySet[DataEvent]:
    return DataEvent.objects.filter(tenant=tenant, direction__in=OUTBOUND_DIRECTIONS)


def list_endpoint_nodes(tenant) -> list[EndpointNode]:
    """Return one ``EndpointNode`` per outbound (service, endpoint, method) tuple."""

    base = _outbound_events(tenant).select_related("external_service")
    grouped = (
        base.values("external_service_id", "endpoint", "method")
        .annotate(
            event_count=Count("id"),
            last_seen=Max("timestamp"),
            first_seen=Min("timestamp"),
        )
        .order_by("-last_seen")
    )

    nodes: list[EndpointNode] = []
    for row in grouped:
        node_qs = base.filter(
            external_service_id=row["external_service_id"],
            endpoint=row["endpoint"],
            method=row["method"],
        )
        node = _build_node(row, node_qs)
        nodes.append(node)
    return nodes


def get_endpoint_node(tenant, node_id: str) -> EndpointNode | None:
    svc_id, endpoint, method = decode_endpoint_id(node_id)
    qs = _outbound_events(tenant).filter(
        external_service_id=svc_id, endpoint=endpoint, method=method
    ).select_related("external_service")
    agg = qs.aggregate(
        event_count=Count("id"), last_seen=Max("timestamp"), first_seen=Min("timestamp")
    )
    if not agg["event_count"]:
        return None
    row = {
        "external_service_id": svc_id,
        "endpoint": endpoint,
        "method": method,
        **agg,
    }
    return _build_node(row, qs)


@dataclass
class EventTrace:
    focal: DataEvent
    inbound: list[DataEvent]
    outbound: DataEvent | None
    asset: DataAsset


def event_trace(tenant, event_id) -> EventTrace | None:
    """Return inbound/outbound DataEvents correlated with ``event_id`` via ``request_id``.

    The focal event identifies the request being traced. Correlated events share
    the same non-empty ``request_id`` within the tenant. If the focal event is
    outbound, that event is returned as ``outbound``; otherwise the most recent
    outbound event sharing the request_id is used (may be ``None``).
    """

    try:
        focal = (
            DataEvent.objects.filter(tenant=tenant, pk=event_id)
            .select_related("data_asset", "external_service")
            .first()
        )
    except (ValueError, ValidationError):
        return None
    if focal is None:
        return None

    correlated: list[DataEvent] = []
    if focal.request_id:
        correlated = list(
            DataEvent.objects.filter(tenant=tenant, request_id=focal.request_id)
            .exclude(pk=focal.pk)
            .select_related("data_asset", "external_service")
            .order_by("timestamp")
        )

    inbound = [e for e in correlated if e.direction == "inbound"]
    if focal.direction == "inbound":
        inbound = sorted([focal, *inbound], key=lambda e: e.timestamp)
        outbound_candidates = [e for e in correlated if e.direction in OUTBOUND_DIRECTIONS]
        outbound = outbound_candidates[-1] if outbound_candidates else None
    else:
        outbound = focal

    return EventTrace(focal=focal, inbound=inbound, outbound=outbound, asset=focal.data_asset)


def endpoint_node_events(tenant, node_id: str) -> QuerySet[DataEvent]:
    svc_id, endpoint, method = decode_endpoint_id(node_id)
    return (
        _outbound_events(tenant)
        .filter(external_service_id=svc_id, endpoint=endpoint, method=method)
        .select_related("data_asset", "external_service")
        .order_by("-timestamp")
    )


def _build_node(row: dict, qs: QuerySet[DataEvent]) -> EndpointNode:
    sample = qs.first()
    svc = sample.external_service if sample else None

    asset_rows = (
        qs.values("data_asset__name", "data_asset__label")
        .annotate(count=Count("id"))
        .order_by("-count", "data_asset__name")
    )
    assets = [
        AssetCount(
            name=r["data_asset__name"],
            label=r["data_asset__label"],
            count=r["count"],
        )
        for r in asset_rows
    ]

    worst = _worst_outcome(qs.values_list("outcome", flat=True).distinct())

    last_seen: datetime = row["last_seen"]
    sparkline = _hourly_buckets(qs, end=last_seen)

    return EndpointNode(
        id=_encode_id(row["external_service_id"], row["endpoint"], row["method"]),
        external_service_id=svc.id if svc else None,
        external_service_name=svc.name if svc else None,
        external_service_domain=svc.domain if svc else None,
        endpoint=row["endpoint"],
        method=row["method"],
        direction="outbound",
        worst_outcome=worst,
        event_count=row["event_count"],
        last_seen=last_seen,
        first_seen=row["first_seen"],
        assets=assets,
        sparkline=sparkline,
    )


def _worst_outcome(outcomes: Iterable[str]) -> str:
    return max(outcomes, key=lambda o: OUTCOME_RANK.get(o, -1), default="expected")


def _hourly_buckets(qs: QuerySet[DataEvent], *, end: datetime) -> list[HourBucket]:
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    window_start = end - SPARKLINE_WINDOW
    rows = (
        qs.filter(timestamp__gte=window_start)
        .annotate(hour=TruncHour("timestamp"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )
    return [HourBucket(hour=r["hour"], count=r["count"]) for r in rows]
