"""``wiregraph_doctor`` must run cleanly without DRF on the import path.

Specifically, the ``_check_api_extra`` step should report the API extra as
not installed (rather than crashing) when DRF cannot be imported.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

import wiregraph


# JWTAuthMiddleware is omitted via include_jwt=False — the realistic shape
# of MIDDLEWARE in a no-DRF install.
NO_DRF_MIDDLEWARE = wiregraph.setup(
    ["django.contrib.auth.middleware.AuthenticationMiddleware"],
    include_jwt=False,
)


@override_settings(WIREGRAPH={"ENABLED": True}, MIDDLEWARE=NO_DRF_MIDDLEWARE)
def test_doctor_reports_api_extra_missing(no_drf):
    out = StringIO()
    err = StringIO()

    try:
        call_command("wiregraph_doctor", stdout=out, stderr=err)
        exit_code = 0
    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    output = out.getvalue()
    assert exit_code == 0, f"doctor failed: {output}\n{err.getvalue()}"
    assert "[FAIL]" not in output
    assert "API extra not installed" in output
