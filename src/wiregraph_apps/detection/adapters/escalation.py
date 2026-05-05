"""Django adapter for :mod:`wiregraph_core.escalation`.

Reads escalation thresholds from settings, injects ``django.core.cache``,
and delegates the daily promotion rollup write to ``persistence``.
"""

from __future__ import annotations

import logging

from wiregraph_apps.common.conf import get_escalation_config
from wiregraph_apps.detection.adapters.cache import get_cache
from wiregraph_core.escalation import should_escalate as _core_should_escalate

logger = logging.getLogger(__name__)


def should_escalate(tenant_id, asset_name: str, domain: str) -> bool:
    threshold, window = get_escalation_config()
    promoted = _core_should_escalate(
        get_cache(), (tenant_id, asset_name, domain), threshold, window
    )
    if promoted:
        from wiregraph_apps.detection.persistence import record_escalation

        record_escalation(tenant_id)
    return promoted
