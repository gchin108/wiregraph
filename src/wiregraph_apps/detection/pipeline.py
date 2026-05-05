"""Detection orchestration entry point.

Wraps the scan → persist → enqueue-async flow that the request middleware
and (eventually) the egress interceptor share. Middleware stays at the HTTP
layer; this module owns the cross-cutting orchestration so the same code
path runs regardless of where the payload originated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wiregraph_apps.detection.persistence import persist_matches
from wiregraph_apps.detection.regex_scanner import RegexScanner
from wiregraph_apps.detection.tasks import enqueue_presidio_scan

if TYPE_CHECKING:
    from wiregraph_apps.detection.models import DataEvent


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
) -> "list[DataEvent]":
    """Scan ``text``, persist any matches, and enqueue the async Presidio pass.

    Returns the persisted ``DataEvent`` rows (empty list if nothing matched
    or there was no tenant). Callers (middleware, egress) handle HTTP-layer
    concerns and tenant resolution; this function owns everything below.
    """
    if tenant is None or not text:
        return []

    matches = _get_scanner().scan(text)
    events: list = []
    if matches:
        events = persist_matches(
            tenant=tenant,
            matches=matches,
            direction=direction,
            endpoint=endpoint,
            method=method,
            detection_method="regex",
            request_id=request_id,
            request=request,
        )
    enqueue_presidio_scan(
        tenant=tenant,
        text=text,
        direction=direction,
        endpoint=endpoint,
        method=method,
        request_id=request_id,
    )
    return events
