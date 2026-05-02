"""Celery tasks for async PII analysis.

``scan_payload_async`` runs Microsoft Presidio over a payload in the worker so
the request/response cycle stays on the fast regex path. The middleware and
egress interceptor enqueue this task when ``WIREGRAPH["ENABLE_PRESIDIO"]`` is
True.
"""

from __future__ import annotations

import logging
from typing import Any

from wiregraph_apps.common.conf import get_config

logger = logging.getLogger(__name__)

TASK_NAME = "wiregraph.detection.scan_payload_async"

try:
    from celery import shared_task

    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CELERY_AVAILABLE = False


def enqueue_presidio_scan(
    *,
    tenant,
    text: str,
    direction: str,
    endpoint: str,
    method: str,
    request_id: str = "",
    external_service_id: Any = None,
) -> None:
    """Enqueue a Presidio scan for a payload. No-op if Presidio or Celery is disabled."""
    if not get_config("ENABLE_PRESIDIO"):
        return
    if not text:
        return
    try:
        # Re-import here so tests can patch the task via this module.
        from wiregraph_apps.detection.tasks import scan_payload_async
    except ImportError:
        logger.debug("wiregraph: celery not installed; skipping presidio enqueue")
        return
    try:
        scan_payload_async.delay(
            tenant_id=tenant.pk,
            text=text,
            direction=direction,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
            external_service_id=external_service_id,
        )
    except Exception:
        logger.exception("wiregraph: failed to enqueue presidio scan")


def _run(
    *,
    tenant_id: Any,
    text: str,
    direction: str,
    endpoint: str,
    method: str,
    request_id: str,
    external_service_id: Any = None,
) -> dict[str, Any]:
    from django.apps import apps

    from wiregraph_apps.detection.persistence import persist_matches
    from wiregraph_core.scanner.presidio import (
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

    external_service = None
    if external_service_id is not None:
        from wiregraph_apps.egress.models import ExternalService

        try:
            external_service = ExternalService.objects.get(pk=external_service_id)
        except ExternalService.DoesNotExist:
            logger.debug(
                "wiregraph: external_service %s not found; scanning without sink",
                external_service_id,
            )

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
        external_service=external_service,
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
        external_service_id: Any = None,
    ) -> dict[str, Any]:
        return _run(
            tenant_id=tenant_id,
            text=text,
            direction=direction,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
            external_service_id=external_service_id,
        )
