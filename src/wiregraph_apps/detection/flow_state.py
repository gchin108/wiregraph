"""First-sight checks for ``(tenant, asset, service)`` flows.

Used by the classifier to mark new flows. Kept separate from
``selectors.py`` (dashboard-shaped reads) so the detection pipeline does
not pull in DRF-adjacent code.
"""

from __future__ import annotations

from wiregraph_apps.detection.models import DataEvent


def is_new_flow(tenant, data_asset, external_service) -> bool:
    """First sight of the ``(tenant, asset, service)`` triple?"""
    return not DataEvent.objects.filter(
        tenant=tenant,
        data_asset=data_asset,
        external_service=external_service,
    ).exists()


def is_new_flow_for_event(tenant, data_event, external_service) -> bool:
    """Like :func:`is_new_flow` but excludes ``data_event`` itself, so the
    classifier can call this *after* the freshly persisted row exists."""
    return (
        not DataEvent.objects.filter(
            tenant=tenant,
            data_asset=data_event.data_asset,
            external_service=external_service,
        )
        .exclude(pk=data_event.pk)
        .exists()
    )
