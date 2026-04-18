"""Celery tasks for async PII analysis.

``scan_payload_async`` runs Microsoft Presidio over a payload in the worker so
the request/response cycle stays on the fast regex path. The middleware
enqueues this task when ``WIREGRAPH["ENABLE_PRESIDIO"]`` is True.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TASK_NAME = "wiregraph.detection.scan_payload_async"

try:
    from celery import shared_task

    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CELERY_AVAILABLE = False


def _run(
    *,
    tenant_id: Any,
    text: str,
    direction: str,
    endpoint: str,
    method: str,
    request_id: str,
) -> dict[str, Any]:
    from django.apps import apps

    from wiregraph_apps.common.conf import get_config
    from wiregraph_apps.detection.persistence import persist_matches
    from wiregraph_apps.detection.presidio_scanner import (
        PresidioScanner,
        dedupe_against,
    )
    from wiregraph_apps.detection.regex_scanner import RegexScanner

    if not get_config("ENABLE_PRESIDIO"):
        return {"skipped": "ENABLE_PRESIDIO is False"}

    tenant_label = get_config("TENANT_MODEL")
    Tenant = apps.get_model(tenant_label)
    try:
        tenant = Tenant.objects.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        logger.warning("wiregraph: tenant %s not found; skipping presidio scan", tenant_id)
        return {"skipped": "tenant not found"}

    presidio_matches = PresidioScanner().scan(text)
    regex_matches = RegexScanner().scan(text)
    deduped = dedupe_against(presidio_matches, regex_matches)
    if not deduped:
        return {"persisted": 0}

    events = persist_matches(
        tenant=tenant,
        matches=deduped,
        direction=direction,
        endpoint=endpoint,
        method=method,
        detection_method="presidio",
        request_id=request_id,
    )
    return {"persisted": len(events)}


if _CELERY_AVAILABLE:

    @shared_task(name=TASK_NAME)
    def scan_payload_async(
        tenant_id: Any,
        text: str,
        *,
        direction: str,
        endpoint: str,
        method: str,
        request_id: str = "",
    ) -> dict[str, Any]:
        return _run(
            tenant_id=tenant_id,
            text=text,
            direction=direction,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
        )
