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

from django.db.models import Count, Max, Min, QuerySet
from django.db.models.functions import TruncHour

from wiregraph_apps.detection.models import DataEvent

OUTCOME_RANK = {"expected": 0, "acceptable": 1, "suspicious": 2, "prohibited": 3}
SPARKLINE_WINDOW = timedelta(days=7)


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
    external_service_id: int | None
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


def _encode_id(external_service_id: int | None, endpoint: str, method: str) -> str:
    raw = f"{external_service_id or ''}|{method}|{endpoint}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_endpoint_id(node_id: str) -> tuple[int | None, str, str]:
    padding = "=" * (-len(node_id) % 4)
    try:
        raw = base64.urlsafe_b64decode(node_id + padding).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Invalid endpoint node id") from exc
    svc, method, endpoint = raw.split("|", 2)
    return (int(svc) if svc else None), endpoint, method


def _outbound_events(tenant) -> QuerySet[DataEvent]:
    return DataEvent.objects.filter(tenant=tenant, direction="outbound")


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
