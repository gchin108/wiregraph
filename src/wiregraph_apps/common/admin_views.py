"""Admin data flow graph dashboard.

Renders a three-column directed graph of observed PII flows:
    inbound endpoint  →  PII type (DataAsset)  →  external service

The page extends ``admin/base_site.html`` so it looks native inside Django
admin and inherits auth. Graph rendering is done client-side with D3.js
loaded via CDN (no build step, no new Python deps).

Data is aggregated server-side, scoped to tenants the current user belongs
to, and filtered by optional ``start`` and ``end`` query parameters
(``YYYY-MM-DD``). The JSON blob returned via ``?format=json`` is the same
graph shape consumed by the template — reused for refresh-in-place.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import View

from wiregraph_apps.detection.models import DataEvent


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _tenant_ids_for_user(user) -> list:
    if user.is_superuser:
        from wiregraph_apps.tenants.models import Tenant

        return list(Tenant.objects.values_list("pk", flat=True))
    return list(user.tenant_memberships.values_list("tenant_id", flat=True))


def _build_graph(user, start, end) -> dict:
    tenant_ids = _tenant_ids_for_user(user)
    qs = DataEvent.objects.filter(tenant_id__in=tenant_ids)

    if start:
        qs = qs.filter(timestamp__gte=datetime.combine(start, time.min))
    if end:
        qs = qs.filter(timestamp__lt=datetime.combine(end + timedelta(days=1), time.min))

    # Inbound + outbound endpoints → asset (rendered in separate sub-groups).
    # Also group by detection_method so tooltips can name the detector; we
    # collapse back in Python by picking the most-common one per edge.
    inbound = (
        qs.filter(direction__in=["inbound", "outbound"])
        .values(
            "endpoint", "direction",
            "data_asset__name", "data_asset__label",
            "outcome", "detection_method",
        )
        .annotate(n=Count("id"), max_conf=Max("confidence"))
    )
    # Asset → external service (egress). The interceptor has historically
    # written either "egress" or "wiregraph_egress"; accept both.
    egress = (
        qs.filter(direction__in=["egress", "wiregraph_egress"], external_service__isnull=False)
        .values(
            "data_asset__name", "data_asset__label",
            "external_service__domain", "external_service__name",
            "outcome", "detection_method",
        )
        .annotate(n=Count("id"), max_conf=Max("confidence"))
    )

    endpoints: dict[tuple[str, str], int] = {}
    assets: dict[str, dict] = {}
    services: dict[str, dict] = {}
    counts = {"expected": 0, "acceptable": 0, "suspicious": 0, "prohibited": 0}

    # Buckets keyed by (source, target, outcome). Splitting the SQL group by
    # detection_method lets us rank detectors per edge while still folding
    # them into a single visual edge here.
    edge_buckets: dict[tuple[str, str, str], dict] = {}

    def _bucket(key: tuple[str, str, str]) -> dict:
        b = edge_buckets.get(key)
        if b is None:
            b = {"weight": 0, "max_conf": 0.0, "detectors": Counter()}
            edge_buckets[key] = b
        return b

    for row in inbound:
        ep = row["endpoint"] or "/"
        direction = row["direction"]
        asset_name = row["data_asset__name"]
        outcome = row["outcome"] or "expected"
        n = row["n"]
        endpoints[(direction, ep)] = endpoints.get((direction, ep), 0) + n
        assets.setdefault(
            asset_name, {"name": asset_name, "label": row["data_asset__label"], "count": 0}
        )["count"] += n
        counts[outcome] = counts.get(outcome, 0) + n
        bucket = _bucket((f"endpoint::{direction}::{ep}", f"asset::{asset_name}", outcome))
        bucket["weight"] += n
        bucket["max_conf"] = max(bucket["max_conf"], row["max_conf"] or 0.0)
        bucket["detectors"][row["detection_method"] or ""] += n

    for row in egress:
        asset_name = row["data_asset__name"]
        domain = row["external_service__domain"]
        outcome = row["outcome"] or "expected"
        n = row["n"]
        assets.setdefault(
            asset_name, {"name": asset_name, "label": row["data_asset__label"], "count": 0}
        )["count"] += n
        services.setdefault(
            domain,
            {"domain": domain, "name": row["external_service__name"], "count": 0},
        )["count"] += n
        counts[outcome] = counts.get(outcome, 0) + n
        bucket = _bucket((f"asset::{asset_name}", f"service::{domain}", outcome))
        bucket["weight"] += n
        bucket["max_conf"] = max(bucket["max_conf"], row["max_conf"] or 0.0)
        bucket["detectors"][row["detection_method"] or ""] += n

    # Origin lookup: for each asset→service edge, find the inbound endpoint
    # whose request_id matches one of the egress events on that pair. Picks
    # the most-common origin when several inbound requests share a target.
    egress_pairs_to_rids: dict[tuple[str, str], set[str]] = defaultdict(set)
    egress_rid_rows = (
        qs.filter(
            direction__in=["egress", "wiregraph_egress"],
            external_service__isnull=False,
        )
        .exclude(request_id="")
        .values("data_asset__name", "external_service__domain", "request_id")
    )
    all_rids: set[str] = set()
    for row in egress_rid_rows:
        rid = row["request_id"]
        egress_pairs_to_rids[(row["data_asset__name"], row["external_service__domain"])].add(rid)
        all_rids.add(rid)

    inbound_endpoint_by_rid: dict[str, str] = {}
    if all_rids:
        for rid, ep in qs.filter(direction="inbound", request_id__in=all_rids).values_list(
            "request_id", "endpoint"
        ):
            # First write wins — multiple inbound rows for the same request
            # share the endpoint, so it doesn't matter which we pick.
            inbound_endpoint_by_rid.setdefault(rid, ep or "/")

    origin_by_pair: dict[tuple[str, str], str] = {}
    for pair, rids in egress_pairs_to_rids.items():
        endpoints_seen = Counter(
            inbound_endpoint_by_rid[rid] for rid in rids if rid in inbound_endpoint_by_rid
        )
        if endpoints_seen:
            origin_by_pair[pair] = endpoints_seen.most_common(1)[0][0]

    edges: list[dict] = []
    for (source, target, outcome), b in edge_buckets.items():
        primary_detector = b["detectors"].most_common(1)[0][0] if b["detectors"] else ""
        edge: dict = {
            "source": source,
            "target": target,
            "outcome": outcome,
            "weight": b["weight"],
            "detector": primary_detector,
            "confidence": round(b["max_conf"], 2) if b["max_conf"] else None,
        }
        if source.startswith("endpoint::"):
            # Inbound edge — origin is the source endpoint itself.
            edge["origin_endpoint"] = source.split("::", 2)[2]
        elif source.startswith("asset::") and target.startswith("service::"):
            asset_name = source.split("::", 1)[1]
            domain = target.split("::", 1)[1]
            edge["origin_endpoint"] = origin_by_pair.get((asset_name, domain), "")
        edges.append(edge)

    return {
        "endpoints": [
            {
                "id": f"endpoint::{direction}::{ep}",
                "label": ep,
                "direction": direction,
                "count": n,
            }
            for (direction, ep), n in sorted(
                endpoints.items(), key=lambda kv: (kv[0][0] != "inbound", -kv[1])
            )
        ],
        "assets": [
            {"id": f"asset::{a['name']}", "label": a["label"] or a["name"], "count": a["count"]}
            for a in sorted(assets.values(), key=lambda a: -a["count"])
        ],
        "services": [
            {"id": f"service::{s['domain']}", "label": s["name"] or s["domain"], "count": s["count"]}
            for s in sorted(services.values(), key=lambda s: -s["count"])
        ],
        "edges": edges,
        "counts": counts,
    }


@method_decorator(staff_member_required, name="dispatch")
class WiregraphDashboardView(View):
    def get(self, request):
        end = _parse_date(request.GET.get("end")) or timezone.localdate()
        start = _parse_date(request.GET.get("start")) or (end - timedelta(days=30))

        graph = _build_graph(request.user, start, end)

        if request.GET.get("format") == "json":
            return JsonResponse({"start": start.isoformat(), "end": end.isoformat(), **graph})

        context = {
            "title": "WireGraph — Data Flow",
            "graph": graph,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "has_data": bool(graph["edges"]),
        }
        return render(request, "admin/wiregraph/dashboard.html", context)
