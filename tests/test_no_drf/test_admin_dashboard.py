"""Bundled admin dashboard must render without DRF on the import path."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

import wiregraph
from tests.fixtures.factories import TenantMembershipFactory


pytestmark = pytest.mark.django_db


# Realistic no-DRF MIDDLEWARE: include_jwt=False mirrors what auto-detection
# would produce in a venv where the [drf] extra isn't installed.
NO_DRF_MIDDLEWARE = wiregraph.setup(
    [
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    include_jwt=False,
)


@override_settings(MIDDLEWARE=NO_DRF_MIDDLEWARE)
def test_admin_dashboard_renders_with_drf_hidden(no_drf):
    User = get_user_model()
    user = User.objects.create_user(username="staff_no_drf", password="pw", is_staff=True)
    TenantMembershipFactory(user=user)

    client = Client()
    client.force_login(user)

    response = client.get("/admin/wiregraph/dashboard/")

    assert response.status_code == 200
    assert b"wiregraph" in response.content.lower()
