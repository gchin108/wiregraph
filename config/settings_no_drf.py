"""Minimal settings used by the no-DRF regression guard subprocess tests.

Mirrors ``config.settings`` with three deliberate omissions:
    * ``rest_framework`` / ``rest_framework_simplejwt`` / ``drf_spectacular``
      are NOT in ``INSTALLED_APPS``.
    * ``JWTAuthMiddleware`` is NOT in ``MIDDLEWARE`` (it requires DRF at
      ``__init__`` time).
    * No ``REST_FRAMEWORK`` / ``SPECTACULAR_SETTINGS`` blocks.

Importing this module must not require ``rest_framework`` to be on the
import path — that's the whole point.
"""

from __future__ import annotations

from pathlib import Path

import wiregraph

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "no-drf-test-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

INSTALLED_APPS = DJANGO_APPS + [*wiregraph.INSTALLED_APPS]

MIDDLEWARE = wiregraph.setup(
    [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ],
    include_jwt=False,
)

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

WIREGRAPH = {"ENABLED": True}
