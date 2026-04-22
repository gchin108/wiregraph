"""Read-only reporting endpoints.

``ShadowReportView`` surfaces the Phase 2 shadow-mode rollup so operators can
see the noise delta between today's alerting and what the new classification
policy would emit, without having to query the admin or the counter model
directly.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from wiregraph_apps.common.tenancy import resolve_tenant
from wiregraph_apps.reporting.models import ShadowDecisionCounter

_ALERTING_LEVELS = {"prohibited", "suspicious"}
_DEFAULT_DAYS = 7
_MAX_DAYS = 90


class ShadowReportView(APIView):
    """Aggregate shadow counters for the caller's tenant.

    Query params:
      - ``days`` (int, default 7, max 90): trailing window.
    """

    def get(self, request):
        tenant = resolve_tenant(request)
        if tenant is None:
            raise PermissionDenied("No tenant membership for this user.")

        try:
            days = int(request.query_params.get("days", _DEFAULT_DAYS))
        except (TypeError, ValueError):
            days = _DEFAULT_DAYS
        days = max(1, min(days, _MAX_DAYS))

        since = (timezone.now() - timedelta(days=days)).date()
        rows = list(
            ShadowDecisionCounter.objects.filter(tenant=tenant, day__gte=since)
            .order_by("-day", "outcome", "shadow_alert_level")
            .values("day", "outcome", "shadow_alert_level", "count")
        )

        total = sum(r["count"] for r in rows)
        shadow_alerts = sum(
            r["count"] for r in rows if r["shadow_alert_level"] in _ALERTING_LEVELS
        )
        downgrades = total - shadow_alerts

        by_outcome: dict[str, int] = {}
        by_level: dict[str, int] = {}
        for r in rows:
            by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + r["count"]
            by_level[r["shadow_alert_level"]] = (
                by_level.get(r["shadow_alert_level"], 0) + r["count"]
            )

        return Response(
            {
                "window_days": days,
                "since": since.isoformat(),
                "totals": {
                    "events": total,
                    # Legacy fires on every detection today, so parity == total.
                    "legacy_would_alert": total,
                    "shadow_would_alert": shadow_alerts,
                    "downgrades": downgrades,
                    "by_outcome": by_outcome,
                    "by_shadow_level": by_level,
                },
                "buckets": [
                    {
                        "day": r["day"].isoformat(),
                        "outcome": r["outcome"],
                        "shadow_alert_level": r["shadow_alert_level"],
                        "count": r["count"],
                    }
                    for r in rows
                ],
            }
        )
