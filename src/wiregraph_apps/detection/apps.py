from django.apps import AppConfig


class DetectionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wiregraph_apps.detection"
    label = "wiregraph_detection"

    def ready(self):
        import wiregraph_apps.detection.signals  # noqa: F401
        import wiregraph_apps.detection.receivers  # noqa: F401

        from wiregraph_apps.common.conf import get_custom_patterns
        from wiregraph_apps.detection.regex_scanner import _compile_custom_patterns

        _compile_custom_patterns(get_custom_patterns())
