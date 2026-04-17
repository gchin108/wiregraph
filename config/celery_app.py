import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("wiregraph")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["core_apps.detection", "core_apps.egress", "core_apps.reporting"])
