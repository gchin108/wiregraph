from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from wiregraph_apps.common.api.auth_views import (
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # JWT Auth
    path("api/v1/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    # API Apps
    path("api/v1/tenants/", include("wiregraph_apps.tenants.api.urls")),
    path("api/v1/detection/", include("wiregraph_apps.detection.api.urls")),
    path("api/v1/egress/", include("wiregraph_apps.egress.api.urls")),
    path("api/v1/reporting/", include("wiregraph_apps.reporting.api.urls")),
    # OpenAPI Schema
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/schema/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="schema-docs"),
]
