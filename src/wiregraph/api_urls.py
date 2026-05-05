"""Library-owned URL configuration for the JSON API surface.

Mount once in a consumer's project ``urls.py``::

    from django.urls import include, path

    urlpatterns = [
        path("admin/", admin.site.urls),
        path("api/v1/", include("wiregraph.api_urls")),
    ]

When the ``[drf]`` extra is not installed, ``urlpatterns`` is empty and
``/api/v1/...`` paths return 404 — admin, custom views and the bundled
``/admin/wiregraph/dashboard/`` continue to work unchanged. Install the
extra (``pip install 'wiregraph[drf]'``) to enable the API.

The mounted prefix is reverse-discoverable as ``wiregraph-api-root`` so
auto-exclusion logic can locate it without hardcoding ``/api/v1/``.
"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.urls import include, path

from wiregraph._drf import drf_available

logger = logging.getLogger(__name__)


def _api_root(request):
    return JsonResponse({"detail": "wiregraph API root"})


urlpatterns: list = []


if drf_available():
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    from wiregraph_apps.common.api.auth_views import (
        ThrottledTokenObtainPairView,
        ThrottledTokenRefreshView,
    )

    urlpatterns = [
        path("", _api_root, name="wiregraph-api-root"),
        path("auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
        path(
            "auth/token/refresh/",
            ThrottledTokenRefreshView.as_view(),
            name="token_refresh",
        ),
        path("tenants/", include("wiregraph_apps.tenants.api.urls")),
        path("detection/", include("wiregraph_apps.detection.api.urls")),
        path("egress/", include("wiregraph_apps.egress.api.urls")),
        path("reporting/", include("wiregraph_apps.reporting.api.urls")),
        path("schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "schema/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="schema-docs",
        ),
    ]
else:
    logger.info(
        "wiregraph: DRF is not installed; JSON API routes are disabled. "
        "Install with `pip install 'wiregraph[drf]'` to enable /api/v1/."
    )
