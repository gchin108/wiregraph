"""Internal helper for gating DRF-dependent code paths behind the ``[drf]`` extra.

The core library and the bundled admin dashboard work without
``djangorestframework`` installed. The JSON API surface (viewsets, serializers,
schema, JWT auth) is opt-in via ``pip install wiregraph[drf]``. Modules that
require DRF should call :func:`require_drf` at import time so a missing extra
surfaces a clear, actionable error instead of a cryptic ``ModuleNotFoundError``.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

_INSTALL_HINT = (
    "wiregraph's REST API surface requires the [drf] extra. "
    "Install it with: pip install 'wiregraph[drf]' "
    "(or 'wiregraph[all]' for everything)."
)


def require_drf() -> None:
    """Raise :class:`ImproperlyConfigured` if DRF is not importable."""
    try:
        import rest_framework  # noqa: F401
    except ImportError as exc:
        raise ImproperlyConfigured(_INSTALL_HINT) from exc


def drf_available() -> bool:
    """Return whether DRF is importable. Useful for conditional URL wiring."""
    try:
        import rest_framework  # noqa: F401
    except ImportError:
        return False
    return True
