from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core_apps.detection.views import (
    DataAssetViewSet,
    DataEventViewSet,
    SummaryStatsView,
)

router = DefaultRouter()
router.register(r"events", DataEventViewSet, basename="event")
router.register(r"assets", DataAssetViewSet, basename="asset")

urlpatterns = [
    path("", include(router.urls)),
    path("stats/summary/", SummaryStatsView.as_view(), name="stats-summary"),
]
