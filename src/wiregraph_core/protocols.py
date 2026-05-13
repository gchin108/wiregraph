"""Host-agnostic protocols for the detection pipeline.

Hosts (Django today, FastAPI next) supply implementations of these
protocols and pass them into :func:`wiregraph_core.pipeline.run_pipeline`.
Nothing in this module knows about ORMs, settings, or signals.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Protocol

from wiregraph_core.types import Match


class Scanner(Protocol):
    """Synchronous text scanner. Returns zero or more ``Match`` records."""

    def scan(self, text: str) -> list[Match]: ...


class DetectionSink(Protocol):
    """Persistence + classification + signal dispatch for matches.

    Two entry points mirror the Django side's bulk and per-match write
    paths. Implementations are responsible for redaction, allowlist
    filtering, classification, and any host-specific signal dispatch.

    Return type is opaque to the orchestrator — typically a list of
    persisted event rows (Django ``DataEvent`` instances, SQLAlchemy
    rows, dicts, etc.) that the caller hands back to its HTTP layer.
    """

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
    ) -> list[Any]: ...

    def persist_egress_matches(
        self,
        *,
        tenant: Any,
        matches: Iterable[Match],
        external_service: Any,
        endpoint: str,
        method: str,
        request_id: str,
    ) -> list[Any]: ...


PresidioEnqueue = Callable[..., None]
"""Callable that enqueues an async Presidio scan. Receives the same kwargs
as the Django ``enqueue_presidio_scan`` (tenant, text, direction, endpoint,
method, request_id, external_service_id). Hosts that don't run Presidio
pass ``None`` to :func:`wiregraph_core.pipeline.run_pipeline`."""
