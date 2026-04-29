"""Per-request correlation ID propagation.

Mirrors ``tenancy.py``: a ``ContextVar`` lets code outside the request/response
cycle (notably the egress interceptor running inside user code that calls
``requests``) recover the inbound request's correlation ID without needing an
``HttpRequest``. ``DataEvent.request_id`` written from both directions then
joins inbound and outbound rows for the trace view (Phase 4).

ContextVars propagate to threads created via ``concurrent.futures`` and to
asyncio tasks; for Celery, callers must pass ``request_id`` explicitly (the
detection task already does).
"""

from __future__ import annotations

from contextvars import ContextVar

_current_request_id: ContextVar[str] = ContextVar(
    "wiregraph_current_request_id", default=""
)


def get_current_request_id() -> str:
    return _current_request_id.get()


def set_current_request_id(request_id: str):
    return _current_request_id.set(request_id)


def reset_current_request_id(token) -> None:
    _current_request_id.reset(token)
