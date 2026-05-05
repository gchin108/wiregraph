"""Public signal contract for the egress interceptor.

See :mod:`wiregraph_apps.detection.signals` for the contract conventions
(payload dataclasses are documentation, not runtime validation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.dispatch import Signal


@dataclass(frozen=True)
class EgressPIILeakPayload:
    """Payload for :data:`egress_pii_leak`.

    Attributes:
        data_event: The persisted ``DataEvent`` row (``direction='egress'``,
            ``outcome='prohibited'``).
        external_service: The third-party ``ExternalService`` the call was
            destined for. Always set on this signal.
    """

    data_event: Any
    external_service: Any


egress_pii_leak = Signal()
"""Fired when an outbound HTTP call carries PII classified as ``prohibited``.

Narrower than :data:`wiregraph_apps.detection.signals.event_classified` —
this only fires for the prohibited egress subset, kept as a separate
signal so consumers can wire incident-response tooling without a
branching receiver.

Producer: :func:`wiregraph_apps.detection.persistence.persist_egress_matches`,
gated on ``effective_level == "prohibited"``.

Receivers: none built-in. Consumer-facing extension point. The built-in
Slack/pager alerts ride :data:`event_classified` instead so inbound and
egress prohibited flows alert through one code path.

Payload: see :class:`EgressPIILeakPayload`.
"""
egress_pii_leak.payload_class = EgressPIILeakPayload
