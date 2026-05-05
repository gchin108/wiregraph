"""Detection orchestration entry point.

Wraps the scan → persist → enqueue-async flow that the request middleware
and the egress interceptor share. Middleware/interceptors stay at the HTTP
layer; this module owns the cross-cutting orchestration so the same code
path runs regardless of where the payload originated.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from wiregraph_apps.detection.persistence import (
    persist_egress_matches,
    persist_matches,
)
from wiregraph_apps.detection.regex_scanner import RegexScanner
from wiregraph_apps.detection.tasks import enqueue_presidio_scan

if TYPE_CHECKING:
    from wiregraph_apps.detection.models import DataEvent

logger = logging.getLogger(__name__)


_scanner: RegexScanner | None = None


def _get_scanner() -> RegexScanner:
    global _scanner
    if _scanner is None:
        _scanner = RegexScanner()
    return _scanner


def run_pipeline(
    *,
    tenant,
    text: str,
    direction: str,
    endpoint: str,
    method: str,
    request_id: str = "",
    request=None,
    external_service=None,
    content_type: str = "",
) -> "list[DataEvent]":
    """Scan ``text``, persist any matches, and enqueue the async Presidio pass.

    Returns the persisted ``DataEvent`` rows (empty list if nothing matched
    or there was no tenant). Callers handle HTTP-layer concerns and tenant
    resolution; this function owns scanning, persistence, and async enqueue.

    For ``direction == "egress"`` the per-match egress persistence path is
    used (preserving ``json_path`` per match) and JSON bodies are walked to
    annotate matches with their JSON path.
    """
    if tenant is None or not text:
        return []

    matches = _get_scanner().scan(text)
    events: list = []
    if matches:
        if direction == "egress":
            if "application/json" in content_type.lower():
                matches = _enrich_with_json_path(matches, text)
            events = persist_egress_matches(
                tenant=tenant,
                matches=matches,
                external_service=external_service,
                endpoint=endpoint,
                method=method,
                request_id=request_id,
            )
        else:
            events = persist_matches(
                tenant=tenant,
                matches=matches,
                direction=direction,
                endpoint=endpoint,
                method=method,
                detection_method="regex",
                request_id=request_id,
                request=request,
                external_service=external_service,
            )
    enqueue_presidio_scan(
        tenant=tenant,
        text=text,
        direction=direction,
        endpoint=endpoint,
        method=method,
        request_id=request_id,
        external_service_id=external_service.pk if external_service is not None else None,
    )
    return events


def _walk_json_strings(obj, prefix: str = "body"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_json_strings(value, f"{prefix}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk_json_strings(value, f"{prefix}[{index}]")
    elif isinstance(obj, str):
        yield prefix, obj


def _enrich_with_json_path(matches, body_text):
    try:
        parsed = json.loads(body_text)
    except (ValueError, TypeError):
        return matches
    leaves = list(_walk_json_strings(parsed))
    if not leaves:
        return matches
    enriched = []
    for match in matches:
        path = next((p for p, val in leaves if match.value in val), None)
        enriched.append(replace(match, json_path=path) if path else match)
    return enriched
