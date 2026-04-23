"""Signal receivers for alert notifications.

Phase 3 routes alerts off the new ``event_classified`` signal and branches on
the effective alert level (outcome gated by detector confidence, proposal §4).
The legacy ``pii_detected`` and ``egress_pii_leak`` signals still fire — but
gated on effective level at the dispatch site — so external subscribers keep
working. The library no longer subscribes to them itself (the new
``event_classified`` receiver covers those alerts with the correct semantics).

The outbound POST is marked internal so the egress interceptor does not
re-ingest it (which would cause an infinite loop). If the webhook URL is
unset, receivers no-op. Failures are logged and swallowed — alerting must
never break the request that triggered the detection.
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from wiregraph_apps.common.conf import get_config, get_dedup_windows
from wiregraph_apps.detection.dedup import should_emit
from wiregraph_apps.detection.escalation import should_escalate
from wiregraph_apps.detection.signals import event_classified, new_data_asset_discovered

logger = logging.getLogger(__name__)

_WEBHOOK_TIMEOUT = 5  # seconds


def _post(url: str | None, text: str) -> None:
    if not url:
        return
    try:
        import requests
    except ImportError:
        logger.debug("wiregraph: 'requests' not installed; alert skipped")
        return

    from wiregraph_apps.egress.interceptor import mark_internal_call

    try:
        with mark_internal_call():
            requests.post(url, json={"text": text}, timeout=_WEBHOOK_TIMEOUT)
    except Exception:
        logger.exception("wiregraph: alert webhook POST failed")


def _post_alert(text: str) -> None:
    if get_config("DISABLE_BUILTIN_ALERTS"):
        return
    _post(get_config("ALERT_WEBHOOK_URL"), text)


def _post_pager(text: str) -> None:
    if get_config("DISABLE_BUILTIN_ALERTS"):
        return
    url = get_config("PAGER_WEBHOOK_URL") or get_config("ALERT_WEBHOOK_URL")
    _post(url, text)


def _dedup_key(event, external_service, level: str, include_outcome: bool):
    asset = getattr(event, "data_asset", None)
    asset_name = getattr(asset, "name", "") if asset is not None else ""
    domain = getattr(external_service, "domain", "") if external_service else ""
    parts = [getattr(event, "tenant_id", None), asset_name, domain, level]
    if include_outcome:
        parts.append(getattr(event, "outcome", ""))
    return tuple(parts)


@receiver(event_classified)
def route_classified_event(
    sender,
    data_event,
    external_service,
    effective_level,
    confidence,
    reason,
    **kwargs,
):
    """Branch on effective level and dispatch through the dedup layer.

    - ``prohibited`` → immediate Slack + optional pager; 5-minute dedup
    - ``suspicious`` → Slack; 1-hour dedup (key includes outcome)
    - ``acceptable`` / ``expected`` → no-op here (digest handled in a later step)
    """
    if get_config("DISABLE_BUILTIN_ALERTS"):
        return

    prohibited_window, suspicious_window = get_dedup_windows()
    asset = getattr(data_event, "data_asset", None)
    asset_name = getattr(asset, "name", "") if asset is not None else ""
    domain = getattr(external_service, "domain", "") if external_service else ""
    endpoint = getattr(data_event, "endpoint", "") or ""

    if effective_level == "prohibited":
        key = _dedup_key(data_event, external_service, "prohibited", include_outcome=False)
        if not should_emit(key, prohibited_window):
            return
        text = (
            f":rotating_light: wiregraph: PROHIBITED flow — "
            f"{asset_name} → {domain}{endpoint} ({reason})"
        )
        _post_alert(text)
        _post_pager(text)
        return

    if effective_level == "suspicious":
        tenant_id = getattr(data_event, "tenant_id", None)
        if should_escalate(tenant_id, asset_name, domain):
            key = _dedup_key(
                data_event, external_service, "prohibited", include_outcome=False
            )
            if not should_emit(key, prohibited_window):
                return
            text = (
                f":rotating_light: wiregraph: repeated suspicious flow promoted — "
                f"{asset_name} → {domain}{endpoint} ({reason}) — "
                f"consider an explicit rule"
            )
            _post_alert(text)
            _post_pager(text)
            return

        key = _dedup_key(data_event, external_service, "suspicious", include_outcome=True)
        if not should_emit(key, suspicious_window):
            return
        _post_alert(
            f":warning: wiregraph: suspicious flow — "
            f"{asset_name} → {domain}{endpoint} ({reason})"
        )
        return

    if effective_level == "acceptable":
        from wiregraph_apps.reporting.digest import record_digest_entry

        try:
            record_digest_entry(data_event, external_service)
        except Exception:
            logger.exception("wiregraph: digest entry failed")
        return

    # expected: stored-only.


@receiver(new_data_asset_discovered)
def alert_on_new_asset(sender, data_asset, tenant, **kwargs):
    _post_alert(
        f":new: wiregraph: new PII type observed — {data_asset.label} "
        f"({data_asset.name})"
    )
