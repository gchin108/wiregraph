from django.apps import AppConfig


class DetectionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core_apps.detection"

    def ready(self):
        import core_apps.detection.signals  # noqa: F401
        import core_apps.detection.receivers  # noqa: F401
