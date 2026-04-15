from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_apps.common"

    def ready(self):
        self._register_admin_dashboard()

    @staticmethod
    def _register_admin_dashboard():
        from django.contrib import admin
        from django.urls import path

        from core_apps.common.admin_views import WiregraphDashboardView

        original_get_urls = admin.site.get_urls

        def get_urls():
            custom = [
                path(
                    "wiregraph/dashboard/",
                    admin.site.admin_view(WiregraphDashboardView.as_view()),
                    name="wiregraph_dashboard",
                ),
            ]
            return custom + original_get_urls()

        admin.site.get_urls = get_urls
