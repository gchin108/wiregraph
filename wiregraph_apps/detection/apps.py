from django.apps import AppConfig


class DetectionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wiregraph_apps.detection"

    def ready(self):
        import wiregraph_apps.detection.signals  # noqa: F401
        import wiregraph_apps.detection.receivers  # noqa: F401
