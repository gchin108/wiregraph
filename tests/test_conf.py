from django.test import override_settings

from core_apps.common.conf import DEFAULTS, get_config, is_enabled


def test_defaults_returned_when_unset():
    with override_settings(WIREGRAPH={}):
        for key, default in DEFAULTS.items():
            assert get_config(key) == default


def test_enabled_defaults_false():
    with override_settings(WIREGRAPH={}):
        assert is_enabled() is False


def test_enabled_reflects_user_override():
    with override_settings(WIREGRAPH={"ENABLED": True}):
        assert is_enabled() is True


def test_user_override_wins():
    with override_settings(WIREGRAPH={"DATA_RETENTION_DAYS": 7, "SAMPLING_RATE": 0.25}):
        assert get_config("DATA_RETENTION_DAYS") == 7
        assert get_config("SAMPLING_RATE") == 0.25
        assert get_config("REDACT_STRATEGY") == DEFAULTS["REDACT_STRATEGY"]


def test_missing_wiregraph_setting_uses_defaults():
    # Simulate a project that hasn't defined WIREGRAPH at all.
    with override_settings():
        from django.conf import settings

        if hasattr(settings, "WIREGRAPH"):
            delattr(settings, "WIREGRAPH")
        assert get_config("ENABLED") is False
        assert get_config("MAX_BODY_SIZE") == 1_048_576
