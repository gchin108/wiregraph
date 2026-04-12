from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    # JWT Auth
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # API Apps
    path("api/v1/tenants/", include("core_apps.tenants.urls")),
    path("api/v1/detection/", include("core_apps.detection.urls")),
    path("api/v1/egress/", include("core_apps.egress.urls")),
    path("api/v1/reporting/", include("core_apps.reporting.urls")),
    # OpenAPI Schema
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/schema/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="schema-docs"),
]
