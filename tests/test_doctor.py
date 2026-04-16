"""Tests for the ``wiregraph_doctor`` management command."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from wiregraph.setup import DJANGO_AUTH, JWT_AUTH, PII_DETECTION


def _run():
    out = StringIO()
    err = StringIO()
    try:
        call_command("wiregraph_doctor", stdout=out, stderr=err)
        exit_code = 0
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
    return exit_code, out.getvalue(), err.getvalue()


GOOD_MIDDLEWARE = [DJANGO_AUTH, JWT_AUTH, PII_DETECTION]


@override_settings(
    WIREGRAPH={"ENABLED": True},
    MIDDLEWARE=GOOD_MIDDLEWARE,
)
def test_doctor_ok_on_good_config():
    code, out, _ = _run()
    assert "[FAIL]" not in out
    assert "ENABLED=True" in out
    assert "MIDDLEWARE order looks correct" in out


@override_settings(
    WIREGRAPH={"ENABLED": True},
    MIDDLEWARE=[DJANGO_AUTH, PII_DETECTION, JWT_AUTH],  # JWT after PII is wrong
)
def test_doctor_detects_wrong_middleware_order():
    code, out, err = _run()
    assert code == 1
    assert "[FAIL]" in out
    assert "JWTAuthMiddleware must precede" in out


@override_settings(
    WIREGRAPH={"ENABLED": True},
    MIDDLEWARE=[DJANGO_AUTH, JWT_AUTH],  # PII middleware missing
)
def test_doctor_detects_missing_pii_middleware():
    code, out, _ = _run()
    assert code == 1
    assert "missing from MIDDLEWARE" in out


@override_settings(
    WIREGRAPH={"ENABLED": False},
    MIDDLEWARE=GOOD_MIDDLEWARE,
)
def test_doctor_warns_on_disabled():
    code, out, _ = _run()
    assert "[WARN]" in out
    assert "middleware is inert" in out


@override_settings(
    WIREGRAPH={
        "ENABLED": True,
        "ENABLE_EGRESS_TRACKING": True,
        "DISABLE_EGRESS_PATCHING": True,
    },
    MIDDLEWARE=GOOD_MIDDLEWARE,
)
def test_doctor_warns_on_conflicting_egress_config():
    code, out, _ = _run()
    assert "DISABLE_EGRESS_PATCHING=True" in out
