"""Runtime PII detection middleware.

Scans inbound request bodies and outbound response bodies for PII using the
regex scanner, and persists redacted ``DataEvent`` rows scoped to the
authenticated tenant.

Performance guards (checked in this order):
    1. ``EXCLUDED_PATHS`` prefix match
    2. ``SAMPLING_RATE`` random gate
    3. ``MAX_BODY_SIZE`` body length check (skips scan, not the response)
    4. Tenant resolution — requests without a tenant are skipped silently
"""

from __future__ import annotations

import logging
import random
import uuid

from wiregraph_apps.common.conf import (
    get_config,
    get_excluded_paths,
    get_max_body_size,
    get_sampling_rate,
)
from wiregraph_apps.common.request_context import (
    reset_current_request_id,
    set_current_request_id,
)
from wiregraph_apps.common.tenancy import (
    reset_current_tenant,
    resolve_tenant,
    set_current_tenant,
)
from wiregraph_apps.detection.persistence import persist_matches
from wiregraph_apps.detection.regex_scanner import RegexScanner
from wiregraph_apps.detection.tasks import enqueue_presidio_scan

logger = logging.getLogger(__name__)

_SCANNABLE_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/",
)

_REQUEST_ID_ATTR = "_wiregraph_request_id"


class PIIDetectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.scanner = RegexScanner()

    def __call__(self, request):
        skip_scan = self._should_skip(request)

        token = None
        rid_token = None
        if not skip_scan:
            request_id = uuid.uuid4().hex
            setattr(request, _REQUEST_ID_ATTR, request_id)
            rid_token = set_current_request_id(request_id)
            self._scan_inbound(request)
            token = set_current_tenant(resolve_tenant(request))

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
            if rid_token is not None:
                reset_current_request_id(rid_token)

        if not skip_scan:
            self._scan_outbound(request, response)

        return response

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _should_skip(self, request) -> bool:
        path = request.path
        for prefix in get_excluded_paths():
            if path.startswith(prefix):
                return True

        rate = get_sampling_rate()
        if rate < 1.0 and random.random() >= rate:
            return True

        return False

    def _body_too_large(self, content_length: int | None) -> bool:
        if content_length is None:
            return False
        return content_length > get_max_body_size()

    def _is_scannable(self, content_type: str) -> bool:
        if not content_type:
            return False
        ct = content_type.split(";", 1)[0].strip().lower()
        return any(ct.startswith(prefix) or ct == prefix.rstrip("/") for prefix in _SCANNABLE_CONTENT_TYPES)

    # ------------------------------------------------------------------
    # Scans
    # ------------------------------------------------------------------

    def _scan_inbound(self, request) -> None:
        if not self._is_scannable(request.META.get("CONTENT_TYPE", "")):
            return
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0) or None
        except (TypeError, ValueError):
            length = None
        if self._body_too_large(length):
            return

        body = getattr(request, "body", b"") or b""
        if not body:
            return
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            return

        matches = self.scanner.scan(text)
        tenant = resolve_tenant(request)
        if tenant is None:
            logger.debug("wiregraph: no tenant for request %s; skipping", request.path)
            return

        request_id = getattr(request, _REQUEST_ID_ATTR, "")
        if matches:
            persist_matches(
                tenant=tenant,
                matches=matches,
                direction="inbound",
                endpoint=request.path,
                method=request.method or "",
                detection_method="regex",
                request_id=request_id,
                request=request,
            )
        enqueue_presidio_scan(
            tenant=tenant,
            text=text,
            direction="inbound",
            endpoint=request.path,
            method=request.method or "",
            request_id=request_id,
        )

    def _scan_outbound(self, request, response) -> None:
        if getattr(response, "streaming", False):
            return
        if not self._is_scannable(response.get("Content-Type", "")):
            return
        content = getattr(response, "content", b"") or b""
        if len(content) > get_max_body_size():
            return
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            return

        matches = self.scanner.scan(text)
        tenant = resolve_tenant(request)
        if tenant is None:
            logger.debug("wiregraph: no tenant for response %s; skipping", request.path)
            return

        request_id = getattr(request, _REQUEST_ID_ATTR, "")
        if matches:
            persist_matches(
                tenant=tenant,
                matches=matches,
                direction="outbound",
                endpoint=request.path,
                method=request.method or "",
                detection_method="regex",
                request_id=request_id,
                request=request,
            )
        enqueue_presidio_scan(
            tenant=tenant,
            text=text,
            direction="outbound",
            endpoint=request.path,
            method=request.method or "",
            request_id=request_id,
        )
