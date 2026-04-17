"""Installed-apps constant for one-line consumer setup.

Django requires each app to be listed individually in ``INSTALLED_APPS`` for
its models and migrations to register. Rather than asking consumers to paste
five entries in the correct order, they can spread this list:

    INSTALLED_APPS = [
        "django.contrib.admin",
        # ...
        *wiregraph.INSTALLED_APPS,
    ]

Order within the list is dependency-correct: ``common`` and ``tenants`` load
before the apps that reference their models.
"""

from __future__ import annotations

INSTALLED_APPS: list[str] = [
    "wiregraph_apps.common",
    "wiregraph_apps.tenants",
    "wiregraph_apps.detection",
    "wiregraph_apps.egress",
    "wiregraph_apps.reporting",
]
