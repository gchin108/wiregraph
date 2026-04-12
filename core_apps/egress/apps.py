from django.apps import AppConfig


class EgressConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_apps.egress"

    def ready(self):
        import core_apps.egress.signals  # noqa: F401
