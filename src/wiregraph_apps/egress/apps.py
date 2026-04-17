from django.apps import AppConfig


class EgressConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wiregraph_apps.egress"
    label = "wiregraph_egress"

    def ready(self):
        import wiregraph_apps.egress.signals  # noqa: F401
        from wiregraph_apps.egress.interceptor import install_egress_patch

        install_egress_patch()
