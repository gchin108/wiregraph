from django.urls import path

from wiregraph_apps.reporting.api.views import DigestReportView, ShadowReportView

urlpatterns = [
    path("shadow/", ShadowReportView.as_view(), name="reporting-shadow"),
    path("digest/", DigestReportView.as_view(), name="reporting-digest"),
]
