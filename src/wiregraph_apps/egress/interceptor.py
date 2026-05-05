"""Outbound HTTP egress interception.

Monkey-patches ``requests.Session.send`` at app startup so every outbound
``requests``-based HTTP call is recorded as an ``ExternalService`` touch and
handed to :func:`wiregraph_apps.detection.pipeline.run_pipeline`. Matches
create ``DataEvent`` rows with ``direction='egress'`` and fire the
``egress_pii_leak`` signal.

Scope & limits:
    * Only ``requests``-based traffic. ``httpx``/``aiohttp``/raw sockets are
      out of scope (see blueprint §2, Phase 2).
    * Tenant is read from the ``current_tenant`` ContextVar populated by
      ``PIIDetectionMiddleware``. Calls made outside a request cycle without
      an explicit ``set_current_tenant`` are skipped (logged at DEBUG).
    * ``MAX_BODY_SIZE`` caps the body scanned. Larger bodies still create an
      ``ExternalService`` touch but no ``DataEvent``.

Recursion safety:
    Alert webhooks and any other internal traffic must not be re-intercepted.
    A thread-local flag guards re-entry; callers sending internal traffic
    should use ``mark_internal_call()`` as a context manager.

Test hygiene:
    ``DISABLE_EGRESS_PATCHING=True`` disables the patch entirely, which lets
    ``responses``/``VCR.py``/``requests-mock`` work without conflict.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from urllib.parse import unquote_plus, urlsplit

from django.utils import timezone

from wiregraph_apps.common.conf import get_config, get_max_body_size
from wiregraph_apps.common.request_context import get_current_request_id
from wiregraph_apps.common.tenancy import get_current_tenant
from wiregraph_apps.detection.adapters.sinks import resolve_sink
from wiregraph_apps.detection.pipeline import run_pipeline

logger = logging.getLogger(__name__)

_INTERNAL_HEADER = "X-Wiregraph-Internal"
_reentry = threading.local()
_patch_state = {"installed": False, "original": None}


def _is_internal_call(prepared_request) -> bool:
    if getattr(_reentry, "active", False):
        return True
    headers = getattr(prepared_request, "headers", None) or {}
    return headers.get(_INTERNAL_HEADER) == "1"


@contextlib.contextmanager
def mark_internal_call():
    """Suppress interception for traffic originating inside wiregraph itself."""
    previous = getattr(_reentry, "active", False)
    _reentry.active = True
    try:
        yield
    finally:
        _reentry.active = previous


def install_egress_patch() -> bool:
    """Install the ``requests.Session.send`` patch. Idempotent."""
    if _patch_state["installed"]:
        return False
    if get_config("DISABLE_EGRESS_PATCHING"):
        logger.debug("wiregraph: egress patching disabled by config")
        return False
    if not get_config("ENABLE_EGRESS_TRACKING"):
        logger.debug("wiregraph: egress tracking disabled by config")
        return False

    try:
        import requests
    except ImportError:
        logger.debug("wiregraph: 'requests' not installed; egress patch skipped")
        return False

    original = requests.Session.send
    _patch_state["original"] = original
    _patch_state["installed"] = True

    def patched_send(self, request, **kwargs):
        response = original(self, request, **kwargs)
        try:
            _record_egress(request, response)
        except Exception:
            logger.exception("wiregraph: egress recording failed")
        return response

    patched_send.__wrapped__ = original
    requests.Session.send = patched_send
    return True


def uninstall_egress_patch() -> bool:
    """Restore ``requests.Session.send``. Primarily for tests."""
    if not _patch_state["installed"]:
        return False
    try:
        import requests
    except ImportError:
        return False
    requests.Session.send = _patch_state["original"]
    _patch_state["installed"] = False
    _patch_state["original"] = None
    return True


def _record_egress(prepared_request, response) -> None:
    if _is_internal_call(prepared_request):
        return

    tenant = get_current_tenant()
    if tenant is None:
        logger.debug(
            "wiregraph: no current tenant for egress to %s; skipping",
            getattr(prepared_request, "url", "?"),
        )
        return

    url = getattr(prepared_request, "url", "") or ""
    host = urlsplit(url).netloc
    if not host:
        return

    from wiregraph_apps.egress.models import ExternalService

    now = timezone.now()
    with mark_internal_call():
        sink_info = resolve_sink(host, tenant)
        service, created = ExternalService.objects.get_or_create(
            tenant=tenant,
            domain=host,
            defaults={
                "name": sink_info.display_name or host,
                "first_seen_at": now,
                "last_seen_at": now,
                "category": sink_info.category,
                "trust_tier": sink_info.trust_tier,
                "accepts_assets": sink_info.accepts_assets,
            },
        )
        if not created:
            ExternalService.objects.filter(pk=service.pk).update(last_seen_at=now)

        body_text = _extract_body(prepared_request)
        if body_text is None:
            return

        method = getattr(prepared_request, "method", "") or ""
        endpoint = urlsplit(url).path or "/"

        content_type = (getattr(prepared_request, "headers", None) or {}).get(
            "Content-Type", ""
        )
        if "application/x-www-form-urlencoded" in content_type.lower():
            body_text = unquote_plus(body_text)

        run_pipeline(
            tenant=tenant,
            text=body_text,
            direction="egress",
            endpoint=endpoint,
            method=method,
            request_id=get_current_request_id(),
            external_service=service,
            content_type=content_type,
        )


def _extract_body(prepared_request) -> str | None:
    body = getattr(prepared_request, "body", None)
    if body is None:
        return None

    if isinstance(body, bytes):
        if len(body) > get_max_body_size():
            return None
        try:
            return body.decode("utf-8", errors="replace")
        except Exception:
            return None

    if isinstance(body, str):
        if len(body.encode("utf-8", errors="replace")) > get_max_body_size():
            return None
        return body

    return None
