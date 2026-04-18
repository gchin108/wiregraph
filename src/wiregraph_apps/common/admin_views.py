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

from datetime import datetime, time, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
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

    # Inbound + outbound endpoints → asset (rendered in separate sub-groups)
    inbound = (
        qs.filter(direction__in=["inbound", "outbound"])
        .values("endpoint", "direction", "data_asset__name", "data_asset__label")
        .annotate(n=Count("id"))
    )
    # Asset → external service (egress)
    egress = (
        qs.filter(direction="egress", external_service__isnull=False)
        .values(
            "data_asset__name",
            "data_asset__label",
            "external_service__domain",
            "external_service__name",
        )
        .annotate(n=Count("id"))
    )

    endpoints: dict[tuple[str, str], int] = {}
    assets: dict[str, dict] = {}
    services: dict[str, dict] = {}
    edges: list[dict] = []

    for row in inbound:
        ep = row["endpoint"] or "/"
        direction = row["direction"]
        asset_name = row["data_asset__name"]
        key = (direction, ep)
        endpoints[key] = endpoints.get(key, 0) + row["n"]
        assets.setdefault(
            asset_name, {"name": asset_name, "label": row["data_asset__label"], "count": 0}
        )["count"] += row["n"]
        edges.append(
            {
                "source": f"endpoint::{direction}::{ep}",
                "target": f"asset::{asset_name}",
                "weight": row["n"],
            }
        )

    for row in egress:
        asset_name = row["data_asset__name"]
        domain = row["external_service__domain"]
        assets.setdefault(
            asset_name, {"name": asset_name, "label": row["data_asset__label"], "count": 0}
        )["count"] += row["n"]
        services.setdefault(
            domain,
            {"domain": domain, "name": row["external_service__name"], "count": 0},
        )["count"] += row["n"]
        edges.append(
            {
                "source": f"asset::{asset_name}",
                "target": f"service::{domain}",
                "weight": row["n"],
            }
        )

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
