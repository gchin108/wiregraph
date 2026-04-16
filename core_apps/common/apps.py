from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_apps.common"

    def ready(self):
        self._register_admin_dashboard()

    @staticmethod
    def _register_admin_dashboard():
        from django.urls import path
        from django.utils.module_loading import import_string

        from core_apps.common.admin_views import WiregraphDashboardView
        from core_apps.common.conf import get_config

        site = import_string(get_config("ADMIN_SITE"))

        original_get_urls = site.get_urls

        def get_urls():
            custom = [
                path(
                    "wiregraph/dashboard/",
                    site.admin_view(WiregraphDashboardView.as_view()),
                    name="wiregraph_dashboard",
                ),
            ]
            return custom + original_get_urls()

        site.get_urls = get_urls
