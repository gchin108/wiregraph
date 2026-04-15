"""Signal receivers for alert notifications.

Connects ``pii_detected``, ``new_data_asset_discovered``, and
``egress_pii_leak`` to a Slack-compatible webhook configured via
``WIREGRAPH["ALERT_WEBHOOK_URL"]``.

The outbound POST is marked internal so the egress interceptor does not
re-ingest it (which would cause an infinite loop). If the webhook URL is
unset, receivers no-op. Failures are logged and swallowed — alerting must
never break the request that triggered the detection.
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from core_apps.common.conf import get_config
from core_apps.detection.signals import new_data_asset_discovered, pii_detected
from core_apps.egress.signals import egress_pii_leak

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT = 5  # seconds


def _post_alert(text: str) -> None:
    url = get_config("ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        import requests
    except ImportError:
        logger.debug("wiregraph: 'requests' not installed; alert skipped")
        return

    from core_apps.egress.interceptor import mark_internal_call

    try:
        with mark_internal_call():
            requests.post(url, json={"text": text}, timeout=_WEBHOOK_TIMEOUT)
    except Exception:
        logger.exception("wiregraph: alert webhook POST failed")


@receiver(pii_detected)
def alert_on_pii_detected(sender, data_event, request=None, **kwargs):
    _post_alert(
        f":warning: wiregraph: {data_event.data_asset.name} detected "
        f"({data_event.direction}) at {data_event.method} {data_event.endpoint}"
    )


@receiver(new_data_asset_discovered)
def alert_on_new_asset(sender, data_asset, tenant, **kwargs):
    _post_alert(
        f":new: wiregraph: new PII type observed — {data_asset.label} "
        f"({data_asset.name})"
    )


@receiver(egress_pii_leak)
def alert_on_egress_leak(sender, data_event, external_service, **kwargs):
    _post_alert(
        f":rotating_light: wiregraph: egress PII leak — "
        f"{data_event.data_asset.name} sent to {external_service.domain}"
        f"{data_event.endpoint}"
    )
