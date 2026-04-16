from unittest.mock import patch

from django.test import override_settings

from core_apps.detection.receivers import _post_alert


@override_settings(WIREGRAPH={"ENABLED": True, "ALERT_WEBHOOK_URL": "https://hooks.example.com/x"})
def test_post_alert_sends_when_enabled():
    with patch("requests.post") as mock_post:
        _post_alert("hello")
        assert mock_post.called


@override_settings(
    WIREGRAPH={
        "ENABLED": True,
        "ALERT_WEBHOOK_URL": "https://hooks.example.com/x",
        "DISABLE_BUILTIN_ALERTS": True,
    }
)
def test_post_alert_suppressed_when_disabled():
    with patch("requests.post") as mock_post:
        _post_alert("hello")
        assert not mock_post.called


@override_settings(WIREGRAPH={"ENABLED": True})
def test_post_alert_noop_when_webhook_unset():
    with patch("requests.post") as mock_post:
        _post_alert("hello")
        assert not mock_post.called
