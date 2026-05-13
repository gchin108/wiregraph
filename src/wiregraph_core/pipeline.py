"""Framework-agnostic detection orchestration.

Owns the scan → enrich → persist → enqueue-async flow that every host
shares. Hosts supply a :class:`Scanner`, a :class:`DetectionSink`, and an
optional :data:`PresidioEnqueue`; this module knows nothing about HTTP
layers, ORMs, signals, or settings.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any, Iterable

from wiregraph_core.protocols import DetectionSink, PresidioEnqueue, Scanner
from wiregraph_core.types import Match

logger = logging.getLogger(__name__)


def run_pipeline(
    *,
    scanner: Scanner,
    sink: DetectionSink,
    presidio_enqueue: PresidioEnqueue | None = None,
    tenant: Any,
    text: str,
    direction: str,
    endpoint: str,
    method: str,
    request_id: str = "",
    request: Any = None,
    external_service: Any = None,
    content_type: str = "",
) -> list[Any]:
    """Scan ``text``, persist matches via ``sink``, enqueue the async pass.

    Returns whatever the sink returns (empty list if there's no tenant, no
    text, or no matches). For ``direction == "egress"`` with a JSON
    content type, matches are annotated with their JSON path before
    persistence.
    """
    if tenant is None or not text:
        return []

    matches = scanner.scan(text)
    events: list[Any] = []
    if matches:
        if direction == "egress":
            if "application/json" in content_type.lower():
                matches = enrich_with_json_path(matches, text)
            events = sink.persist_egress_matches(
                tenant=tenant,
                matches=matches,
                external_service=external_service,
                endpoint=endpoint,
                method=method,
                request_id=request_id,
            )
        else:
            events = sink.persist_matches(
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

    if presidio_enqueue is not None:
        presidio_enqueue(
            tenant=tenant,
            text=text,
            direction=direction,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
            external_service_id=getattr(external_service, "pk", None)
            if external_service is not None
            else None,
        )
    return events


def enrich_with_json_path(matches: Iterable[Match], body_text: str) -> list[Match]:
    """Walk a JSON body and annotate each match with the dotted path of the
    leaf string it appears in. Returns the original list unchanged on parse
    failure or empty payloads."""
    try:
        parsed = json.loads(body_text)
    except (ValueError, TypeError):
        return list(matches)
    leaves = list(_walk_json_strings(parsed))
    if not leaves:
        return list(matches)
    enriched: list[Match] = []
    for match in matches:
        path = next((p for p, val in leaves if match.value in val), None)
        enriched.append(replace(match, json_path=path) if path else match)
    return enriched


def _walk_json_strings(obj: Any, prefix: str = "body"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_json_strings(value, f"{prefix}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk_json_strings(value, f"{prefix}[{index}]")
    elif isinstance(obj, str):
        yield prefix, obj
