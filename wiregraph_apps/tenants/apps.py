from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wiregraph_apps.tenants"
    label = "wiregraph_tenants"
