from django.urls import path

from wiregraph_apps.reporting.views import ShadowReportView

urlpatterns = [
    path("shadow/", ShadowReportView.as_view(), name="reporting-shadow"),
]
