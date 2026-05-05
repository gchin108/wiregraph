"""JWT authentication middleware.

DRF's ``JWTAuthentication`` runs at the view layer, which means upstream
middleware (including PII detection) sees ``AnonymousUser`` for JWT-authed
traffic. This middleware decodes the ``Authorization: Bearer <token>`` header
during request processing so downstream middleware can resolve a tenant.

It only acts when ``request.user`` is not already authenticated (e.g. by
Django's session-based ``AuthenticationMiddleware``). Invalid or missing
tokens are ignored silently — authentication enforcement remains the job of
DRF's permission classes at the view layer.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject

from wiregraph._drf import require_drf

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self, get_response):
        require_drf()
        from rest_framework_simplejwt.authentication import JWTAuthentication

        self.get_response = get_response
        self._authenticator = JWTAuthentication()

    def __call__(self, request):
        existing = getattr(request, "user", None)
        if existing is None or not getattr(existing, "is_authenticated", False):
            request.user = SimpleLazyObject(lambda: self._resolve(request))
        return self.get_response(request)

    def _resolve(self, request):
        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

        header = self._authenticator.get_header(request)
        if header is None:
            return AnonymousUser()
        try:
            raw_token = self._authenticator.get_raw_token(header)
            if raw_token is None:
                return AnonymousUser()
            validated = self._authenticator.get_validated_token(raw_token)
            return self._authenticator.get_user(validated)
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            logger.debug("wiregraph: JWT auth failed in middleware: %s", exc)
            return AnonymousUser()
