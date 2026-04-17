"""One-call middleware installer.

Consumers call ``wiregraph.setup(MIDDLEWARE)`` in their Django settings to
insert the two WireGraph middleware at the correct positions without having
to remember the ordering rule (JWT auth → PII detection, both after Django's
``AuthenticationMiddleware``).

Idempotent: calling ``setup`` on a list that already contains the middleware
is a no-op with respect to that entry and will still normalize ordering.
"""

from __future__ import annotations

DJANGO_AUTH = "django.contrib.auth.middleware.AuthenticationMiddleware"
JWT_AUTH = "wiregraph_apps.common.middleware.JWTAuthMiddleware"
PII_DETECTION = "wiregraph_apps.detection.middleware.PIIDetectionMiddleware"


def setup(middleware: list[str]) -> list[str]:
    """Return a new MIDDLEWARE list with WireGraph middleware inserted.

    - ``JWTAuthMiddleware`` is inserted immediately after Django's
      ``AuthenticationMiddleware`` (or appended to the end if the latter is
      absent).
    - ``PIIDetectionMiddleware`` is inserted immediately after
      ``JWTAuthMiddleware``.
    - If either entry is already present, it is moved to the correct position
      rather than duplicated.
    """
    result = [m for m in middleware if m not in (JWT_AUTH, PII_DETECTION)]

    try:
        anchor = result.index(DJANGO_AUTH)
        insert_at = anchor + 1
    except ValueError:
        insert_at = len(result)

    result.insert(insert_at, JWT_AUTH)
    result.insert(insert_at + 1, PII_DETECTION)
    return result
