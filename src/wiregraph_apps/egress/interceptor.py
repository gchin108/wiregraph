"""Outbound HTTP egress interception.

Monkey-patches outbound HTTP client APIs at app startup so every outbound call
is recorded as an ``ExternalService`` touch and handed to
:func:`wiregraph_apps.detection.pipeline.run_pipeline`. Matches create
``DataEvent`` rows with ``direction='egress'`` and fire the ``egress_pii_leak``
signal.

Supported transports:
    * ``requests`` — patches ``requests.Session.send``.
    Additional transports (``httpx``, ``aiohttp``) plug into the same recorder
    via the transport registry below; see ``register_transport``.

Scope & limits:
    * Named HTTP clients only. Raw sockets, ``urllib3`` direct, ``http.client``,
      and gRPC are out of scope.
    * Tenant is read from the ``current_tenant`` ContextVar populated by
      ``PIIDetectionMiddleware``. Calls made outside a request cycle without
      an explicit ``set_current_tenant`` are skipped (logged at DEBUG).
    * ``MAX_BODY_SIZE`` caps the body scanned. Larger bodies still create an
      ``ExternalService`` touch but no ``DataEvent``.

Recursion safety:
    Alert webhooks and any other internal traffic must not be re-intercepted.
    A ``ContextVar`` flag guards re-entry (works across threads *and* async
    ``await`` boundaries); callers sending internal traffic should use
    ``mark_internal_call()`` as a context manager.

Test hygiene:
    ``DISABLE_EGRESS_PATCHING=True`` disables the patch entirely, which lets
    ``responses``/``VCR.py``/``requests-mock`` work without conflict.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar
from typing import Callable
from urllib.parse import unquote_plus, urlsplit

from django.utils import timezone

from wiregraph_apps.common.conf import get_config, get_max_body_size
from wiregraph_apps.common.request_context import get_current_request_id
from wiregraph_apps.common.tenancy import get_current_tenant
from wiregraph_apps.detection.adapters.sinks import resolve_sink
from wiregraph_apps.detection.pipeline import run_pipeline

logger = logging.getLogger(__name__)

_INTERNAL_HEADER = "X-Wiregraph-Internal"
_reentry: ContextVar[bool] = ContextVar("wiregraph_egress_reentry", default=False)


@contextlib.contextmanager
def mark_internal_call():
    """Suppress interception for traffic originating inside wiregraph itself.

    Backed by a ``ContextVar``, so this works inside both threaded and async
    call stacks (the flag propagates across ``await`` boundaries within the
    same task).
    """
    token = _reentry.set(True)
    try:
        yield
    finally:
        _reentry.reset(token)


# ---------------------------------------------------------------------------
# Transport-agnostic recorder
# ---------------------------------------------------------------------------


def record_egress(
    *,
    method: str,
    url: str,
    headers: dict | None,
    body: bytes | str | None,
    internal: bool = False,
) -> None:
    """Record an outbound HTTP call, regardless of which client made it.

    Transport adapters normalize their client-specific request object into
    these primitives and call here. Safe to call from sync contexts; async
    transports should wrap this in ``asgiref.sync.sync_to_async`` since it
    touches the ORM.
    """
    if internal or _reentry.get():
        return
    if headers and _get_header(headers, _INTERNAL_HEADER) == "1":
        return

    tenant = get_current_tenant()
    if tenant is None:
        logger.debug("wiregraph: no current tenant for egress to %s; skipping", url)
        return

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

        body_text = _normalize_body(body)
        if body_text is None:
            return

        endpoint = urlsplit(url).path or "/"
        content_type = _get_header(headers or {}, "Content-Type") or ""
        if "application/x-www-form-urlencoded" in content_type.lower():
            body_text = unquote_plus(body_text)

        run_pipeline(
            tenant=tenant,
            text=body_text,
            direction="egress",
            endpoint=endpoint,
            method=method or "",
            request_id=get_current_request_id(),
            external_service=service,
            content_type=content_type,
        )


def _get_header(headers, name: str) -> str | None:
    """Case-insensitive header lookup against a dict-like mapping."""
    if not headers:
        return None
    target = name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == target:
            return value
    return None


def _normalize_body(body: bytes | str | None) -> str | None:
    if body is None:
        return None
    max_size = get_max_body_size()
    if isinstance(body, bytes):
        if len(body) > max_size:
            return None
        try:
            return body.decode("utf-8", errors="replace")
        except Exception:
            return None
    if isinstance(body, str):
        if len(body.encode("utf-8", errors="replace")) > max_size:
            return None
        return body
    return None


# ---------------------------------------------------------------------------
# Transport registry
# ---------------------------------------------------------------------------


class _TransportAdapter:
    name: str
    install: Callable[[], bool]
    uninstall: Callable[[], bool]
    installed: bool = False

    def __init__(self, name: str, install: Callable[[], bool], uninstall: Callable[[], bool]):
        self.name = name
        self._install = install
        self._uninstall = uninstall

    def install(self) -> bool:
        if self.installed:
            return False
        ok = self._install()
        self.installed = ok
        return ok

    def uninstall(self) -> bool:
        if not self.installed:
            return False
        ok = self._uninstall()
        self.installed = False
        return ok


_transports: list[_TransportAdapter] = []


def register_transport(
    name: str,
    install: Callable[[], bool],
    uninstall: Callable[[], bool],
) -> None:
    """Register a transport adapter. Idempotent by name."""
    for existing in _transports:
        if existing.name == name:
            return
    _transports.append(_TransportAdapter(name, install, uninstall))


def installed_transports() -> list[str]:
    return [t.name for t in _transports if t.installed]


# ---------------------------------------------------------------------------
# requests adapter
# ---------------------------------------------------------------------------


_requests_state: dict = {"original": None}


def _install_requests() -> bool:
    try:
        import requests
    except ImportError:
        logger.debug("wiregraph: 'requests' not installed; egress patch skipped")
        return False

    original = requests.Session.send
    _requests_state["original"] = original

    def patched_send(self, request, **kwargs):
        response = original(self, request, **kwargs)
        try:
            record_egress(
                method=getattr(request, "method", "") or "",
                url=getattr(request, "url", "") or "",
                headers=dict(getattr(request, "headers", None) or {}),
                body=getattr(request, "body", None),
            )
        except Exception:
            logger.exception("wiregraph: egress recording failed")
        return response

    patched_send.__wrapped__ = original
    requests.Session.send = patched_send
    return True


def _uninstall_requests() -> bool:
    try:
        import requests
    except ImportError:
        return False
    original = _requests_state.get("original")
    if original is None:
        return False
    requests.Session.send = original
    _requests_state["original"] = None
    return True


register_transport("requests", _install_requests, _uninstall_requests)


# ---------------------------------------------------------------------------
# httpx adapter (sync client)
# ---------------------------------------------------------------------------


_httpx_state: dict = {"original": None}


def _httpx_body(request) -> bytes | None:
    """Extract a request body from an httpx Request without materializing streams."""
    try:
        content = getattr(request, "content", None)
    except Exception:
        return None
    if content is None:
        return None
    return content if isinstance(content, (bytes, bytearray)) else None


def _install_httpx_sync() -> bool:
    try:
        import httpx
    except ImportError:
        logger.debug("wiregraph: 'httpx' not installed; sync patch skipped")
        return False

    original = httpx.Client.send
    _httpx_state["original"] = original

    def patched_send(self, request, **kwargs):
        response = original(self, request, **kwargs)
        try:
            record_egress(
                method=getattr(request, "method", "") or "",
                url=str(getattr(request, "url", "") or ""),
                headers=dict(getattr(request, "headers", None) or {}),
                body=_httpx_body(request),
            )
        except Exception:
            logger.exception("wiregraph: httpx egress recording failed")
        return response

    patched_send.__wrapped__ = original
    httpx.Client.send = patched_send
    return True


def _uninstall_httpx_sync() -> bool:
    try:
        import httpx
    except ImportError:
        return False
    original = _httpx_state.get("original")
    if original is None:
        return False
    httpx.Client.send = original
    _httpx_state["original"] = None
    return True


register_transport("httpx", _install_httpx_sync, _uninstall_httpx_sync)


# ---------------------------------------------------------------------------
# httpx adapter (async client)
# ---------------------------------------------------------------------------


_httpx_async_state: dict = {"original": None}


def _install_httpx_async() -> bool:
    try:
        import httpx
    except ImportError:
        logger.debug("wiregraph: 'httpx' not installed; async patch skipped")
        return False

    from asgiref.sync import sync_to_async

    original = httpx.AsyncClient.send
    _httpx_async_state["original"] = original
    record_async = sync_to_async(record_egress)

    async def patched_send(self, request, **kwargs):
        response = await original(self, request, **kwargs)
        try:
            await record_async(
                method=getattr(request, "method", "") or "",
                url=str(getattr(request, "url", "") or ""),
                headers=dict(getattr(request, "headers", None) or {}),
                body=_httpx_body(request),
            )
        except Exception:
            logger.exception("wiregraph: httpx async egress recording failed")
        return response

    patched_send.__wrapped__ = original
    httpx.AsyncClient.send = patched_send
    return True


def _uninstall_httpx_async() -> bool:
    try:
        import httpx
    except ImportError:
        return False
    original = _httpx_async_state.get("original")
    if original is None:
        return False
    httpx.AsyncClient.send = original
    _httpx_async_state["original"] = None
    return True


register_transport("httpx_async", _install_httpx_async, _uninstall_httpx_async)


# ---------------------------------------------------------------------------
# aiohttp adapter
# ---------------------------------------------------------------------------


_aiohttp_state: dict = {"original": None}


def _aiohttp_body(kwargs: dict) -> tuple[bytes | str | None, str | None]:
    """Extract a scannable body and inferred content-type from aiohttp kwargs.

    Returns ``(body, content_type)``. ``body`` is ``None`` when the payload is
    a stream, file-like object, or multipart ``FormData`` that we don't
    materialize. ``content_type`` is inferred only when the caller used
    ``json=``; otherwise ``None`` and the recorder falls back to the
    request headers.
    """
    import json as _json
    from urllib.parse import urlencode

    if "json" in kwargs and kwargs["json"] is not None:
        try:
            return _json.dumps(kwargs["json"]).encode("utf-8"), "application/json"
        except Exception:
            return None, None

    data = kwargs.get("data")
    if data is None:
        return None, None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data), None
    if isinstance(data, str):
        return data, None
    if isinstance(data, dict):
        try:
            return urlencode(data), "application/x-www-form-urlencoded"
        except Exception:
            return None, None
    return None, None


def _install_aiohttp() -> bool:
    try:
        import aiohttp
    except ImportError:
        logger.debug("wiregraph: 'aiohttp' not installed; patch skipped")
        return False

    from asgiref.sync import sync_to_async

    original = aiohttp.ClientSession._request
    _aiohttp_state["original"] = original
    record_async = sync_to_async(record_egress)

    async def patched_request(self, method, str_or_url, **kwargs):
        response = await original(self, method, str_or_url, **kwargs)
        try:
            body, inferred_ct = _aiohttp_body(kwargs)
            info = getattr(response, "request_info", None)
            url = str(getattr(info, "url", "") or str_or_url)
            headers = dict(getattr(info, "headers", None) or kwargs.get("headers") or {})
            if inferred_ct and not _get_header(headers, "Content-Type"):
                headers["Content-Type"] = inferred_ct
            await record_async(
                method=method or "",
                url=url,
                headers=headers,
                body=body,
            )
        except Exception:
            logger.exception("wiregraph: aiohttp egress recording failed")
        return response

    patched_request.__wrapped__ = original
    aiohttp.ClientSession._request = patched_request
    return True


def _uninstall_aiohttp() -> bool:
    try:
        import aiohttp
    except ImportError:
        return False
    original = _aiohttp_state.get("original")
    if original is None:
        return False
    aiohttp.ClientSession._request = original
    _aiohttp_state["original"] = None
    return True


register_transport("aiohttp", _install_aiohttp, _uninstall_aiohttp)


# ---------------------------------------------------------------------------
# Public install / uninstall API
# ---------------------------------------------------------------------------


def install_egress_patches() -> list[str]:
    """Install every registered transport's monkey-patch. Idempotent.

    Returns the list of transport names that were newly installed this call.
    Honors ``ENABLE_EGRESS_TRACKING`` and ``DISABLE_EGRESS_PATCHING`` config.
    """
    if get_config("DISABLE_EGRESS_PATCHING"):
        logger.debug("wiregraph: egress patching disabled by config")
        return []
    if not get_config("ENABLE_EGRESS_TRACKING"):
        logger.debug("wiregraph: egress tracking disabled by config")
        return []

    newly = []
    for transport in _transports:
        if transport.install():
            newly.append(transport.name)
    if newly:
        logger.debug("wiregraph: egress transports installed: %s", ", ".join(newly))
    return newly


def uninstall_egress_patches() -> list[str]:
    """Restore all installed transports. Primarily for tests."""
    removed = []
    for transport in _transports:
        if transport.uninstall():
            removed.append(transport.name)
    return removed


# ---------------------------------------------------------------------------
# Legacy aliases (deprecated; one-release shim)
# ---------------------------------------------------------------------------


def install_egress_patch() -> bool:
    """Deprecated: use :func:`install_egress_patches`.

    Returns ``True`` if at least one transport was newly installed this call,
    matching the prior single-transport bool contract.
    """
    return bool(install_egress_patches())


def uninstall_egress_patch() -> bool:
    """Deprecated: use :func:`uninstall_egress_patches`."""
    return bool(uninstall_egress_patches())
