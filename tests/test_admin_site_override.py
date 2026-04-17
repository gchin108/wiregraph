"""Verify the admin dashboard attaches to the AdminSite configured via
``WIREGRAPH["ADMIN_SITE"]``.

The registration path in ``CommonConfig.ready()`` is called at Django startup.
We can't easily replay ``ready()`` in a test (Django only fires it once per
process), so we call the private registrar directly with a freshly-
constructed ``AdminSite`` and verify the URL is present.
"""

from django.contrib.admin import AdminSite
from django.test import override_settings

from wiregraph_apps.common.apps import CommonConfig


class _CustomAdminSite(AdminSite):
    pass


_custom_site = _CustomAdminSite(name="custom")


def test_dashboard_url_attached_to_custom_site():
    dotted = f"{__name__}._custom_site"
    with override_settings(WIREGRAPH={"ENABLED": True, "ADMIN_SITE": dotted}):
        CommonConfig._register_admin_dashboard()

    names = [getattr(u, "name", None) for u in _custom_site.get_urls()]
    assert "wiregraph_dashboard" in names
