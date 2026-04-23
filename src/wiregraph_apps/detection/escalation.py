"""Suspicious → prohibited escalation (proposal §5).

After ``ESCALATION_SUSPICIOUS_COUNT`` suspicious hits on the same
``(tenant, asset, service)`` key inside ``ESCALATION_WINDOW_SECONDS``, promote
the next alert to prohibited priority and surface a "consider an explicit
rule" hint.

Counters live in Django's cache (atomic INCR with a sliding TTL). On promotion
the counter is reset and a daily rollup row is upserted so the shadow report
can expose ``suspicious_escalated_total`` — the calibration signal for the
threshold itself (the last open question in the proposal).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Iterable

from django.core.cache import cache

from wiregraph_apps.common.conf import get_escalation_config

logger = logging.getLogger(__name__)

_PREFIX = "wiregraph:esc:"


def _key(parts: Iterable[object]) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}{digest}"


def should_escalate(tenant_id, asset_name: str, domain: str) -> bool:
    """Return True when the *next* suspicious alert for this key should be promoted.

    On return-True the cache counter is reset so the user isn't paged on every
    subsequent suspicious hit — they must accumulate another full window first.
    """
    threshold, window = get_escalation_config()
    if threshold <= 0:
        return False
    key = _key((tenant_id, asset_name, domain))
    # cache.incr raises ValueError if the key is absent; seed with add().
    if cache.add(key, 1, timeout=window):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            # Key expired between add() and incr() — treat as fresh.
            cache.add(key, 1, timeout=window)
            count = 1
    if count >= threshold:
        cache.delete(key)
        _record_promotion(tenant_id)
        return True
    return False


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
