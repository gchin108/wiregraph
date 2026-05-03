"""Django adapter for :mod:`wiregraph_core.escalation`.

Reads escalation thresholds from settings, injects ``django.core.cache``,
and writes the daily promotion rollup row when the pure helper signals an
escalation.
"""

from __future__ import annotations

import logging

from wiregraph_apps.common.conf import get_escalation_config
from wiregraph_apps.detection.adapters.cache import get_cache
from wiregraph_core.escalation import should_escalate as _core_should_escalate

logger = logging.getLogger(__name__)


def should_escalate(tenant_id, asset_name: str, domain: str) -> bool:
    threshold, window = get_escalation_config()
    promoted = _core_should_escalate(
        get_cache(), (tenant_id, asset_name, domain), threshold, window
    )
    if promoted:
        _record_promotion(tenant_id)
    return promoted


def _record_promotion(tenant_id) -> None:
    """Upsert today's escalation rollup row. Best-effort."""
    from django.db.models import F
    from django.utils import timezone

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
