"""Django shim over :func:`wiregraph_core.pipeline.run_pipeline`.

Builds the Django sink + scanner + Celery enqueue once and delegates all
orchestration to the framework-agnostic core. Public signature is
preserved so middleware and the egress interceptor don't change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wiregraph_apps.detection.adapters.sink_django import DjangoSink
from wiregraph_apps.detection.regex_scanner import RegexScanner
from wiregraph_apps.detection.tasks import enqueue_presidio_scan
from wiregraph_core.pipeline import run_pipeline as _core_run_pipeline

if TYPE_CHECKING:
    from wiregraph_apps.detection.models import DataEvent

logger = logging.getLogger(__name__)


_scanner: RegexScanner | None = None
_sink: DjangoSink | None = None


def _get_scanner() -> RegexScanner:
    global _scanner
    if _scanner is None:
        _scanner = RegexScanner()
    return _scanner


def _get_sink() -> DjangoSink:
    global _sink
    if _sink is None:
        _sink = DjangoSink()
    return _sink


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
    return _core_run_pipeline(
        scanner=_get_scanner(),
        sink=_get_sink(),
        presidio_enqueue=enqueue_presidio_scan,
        tenant=tenant,
        text=text,
        direction=direction,
        endpoint=endpoint,
        method=method,
        request_id=request_id,
        request=request,
        external_service=external_service,
        content_type=content_type,
    )
