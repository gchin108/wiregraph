"""Django implementation of :class:`wiregraph_core.protocols.DetectionSink`.

Thin wrapper over the existing :mod:`wiregraph_apps.detection.persistence`
functions so the framework-agnostic orchestrator in
:mod:`wiregraph_core.pipeline` can drive Django writes without importing
Django itself.
"""

from __future__ import annotations

from typing import Any, Iterable

from wiregraph_apps.detection.persistence import (
    persist_egress_matches,
    persist_matches,
)
from wiregraph_core.types import Match


class DjangoSink:
    """Implements ``wiregraph_core.protocols.DetectionSink`` against the ORM."""

    def persist_matches(
        self,
        *,
        tenant: Any,
        matches: Iterable[Match],
        direction: str,
        endpoint: str,
        method: str,
        detection_method: str,
        request_id: str,
        request: Any,
        external_service: Any,
    ) -> list[Any]:
        return persist_matches(
            tenant=tenant,
            matches=matches,
            direction=direction,
            endpoint=endpoint,
            method=method,
            detection_method=detection_method,
            request_id=request_id,
            request=request,
            external_service=external_service,
        )

    def persist_egress_matches(
        self,
        *,
        tenant: Any,
        matches: Iterable[Match],
        external_service: Any,
        endpoint: str,
        method: str,
        request_id: str,
    ) -> list[Any]:
        return persist_egress_matches(
            tenant=tenant,
            matches=matches,
            external_service=external_service,
            endpoint=endpoint,
            method=method,
            request_id=request_id,
        )
