from django.apps import AppConfig


class ReportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wiregraph_apps.reporting"
    label = "wiregraph_reporting"

    def ready(self):
        try:
            import wiregraph.celery  # noqa: F401  — registers the shared_task if Celery is available
        except ImportError:
            pass
