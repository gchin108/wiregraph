"""Pure deterministic classifier for (asset, sink) flows.

Framework-agnostic: no Django, no ORM, no dispatch, no settings reads. Callers
resolve their persistence-layer rows into the dataclasses in
:mod:`wiregraph_core.types`, optionally observe history (``FlowHistory``), and
invoke :func:`classify`.

Classification is deterministic on its inputs. Detector confidence is not an
input here — confidence gates *alerting*, not *classification* (proposal §4),
which is what :func:`effective_alert_level` is for.
"""

from __future__ import annotations

from wiregraph_core.sinks import CATEGORY_DEFAULTS
from wiregraph_core.types import (
    AlertLevel,
    Asset,
    Decision,
    FlowHistory,
    Outcome,
    Policy,
    RuleHit,
    Sink,
)


def effective_accepts(sink: Sink) -> list[str]:
    """Return the effective accept-list for a sink.

    Per-domain ``accepts_assets`` overrides the category default; an empty
    explicit list still means "use category default" (proposal §2, footnote).
    """
    if sink.accepts_assets:
        return list(sink.accepts_assets)
    return list(CATEGORY_DEFAULTS.get(sink.category, []))


def classify(
    asset: Asset,
    sink: Sink,
    rule_hit: RuleHit | None,
    policy: Policy,
    history: FlowHistory | None = None,
) -> Decision:
    """Return the :class:`Decision` for a single (asset, sink) flow.

    ``history`` carries caller-resolved facts the pure classifier cannot
    derive itself (e.g. "is this the first sighting of this triple?"). When
    omitted, defaults to no prior history.
    """
    if rule_hit is not None:
        return Decision(outcome="expected", reason="rule:allowlist")

    accepts = effective_accepts(sink)
    if "*" in accepts or asset.name in accepts:
        return Decision(
            outcome="expected",
            reason=f"category:{sink.category}_accepts_{asset.name}",
        )

    if sink.category == "llm":
        if policy.llm_mode == "strict" and asset.sensitivity_level in {
            "medium",
            "high",
            "critical",
        }:
            return Decision(outcome="prohibited", reason="policy:pii_to_llm")
        if policy.llm_mode == "relaxed" and asset.sensitivity_level in {
            "high",
            "critical",
        }:
            return Decision(outcome="prohibited", reason="policy:sensitive_to_llm")
        # relaxed mode + medium asset → fall through

    if sink.category == "unknown" and asset.sensitivity_level in {"high", "critical"}:
        return Decision(
            outcome="prohibited", reason="policy:sensitive_to_unknown_sink"
        )

    if history is not None and history.is_new_flow:
        return Decision(outcome="suspicious", reason="flow:new_data_flow")

    if sink.trust_tier == "trusted":
        return Decision(
            outcome="acceptable",
            reason=f"trust:trusted_sink_category_{sink.category}",
        )

    if asset.sensitivity_level == "low":
        return Decision(outcome="acceptable", reason="sensitivity:low")

    return Decision(
        outcome="suspicious",
        reason=f"category:{sink.category}_unexpected_{asset.name}",
    )


def effective_alert_level(
    outcome: Outcome,
    confidence: float,
    thresholds: tuple[float, float],
) -> AlertLevel:
    """Map a classification outcome to the level receivers would dispatch on.

    Classification is deterministic; this is where detector confidence gates
    whether a given outcome escalates to a human (proposal §4).

    - Below ``low`` threshold: downgrade noisy matches — ``suspicious`` →
      ``acceptable``, ``prohibited`` → ``suspicious``.
    - At/above ``low`` threshold: no downgrades.
    - ``expected`` and ``acceptable`` are never escalated by confidence alone.
    """
    low, _high = thresholds
    if confidence < low:
        if outcome == "suspicious":
            return "acceptable"
        if outcome == "prohibited":
            return "suspicious"
    return outcome
