"""Unit tests for the pure classifier — no Django imports anywhere.

These mirror the contracts the Django wrapper relies on. If a future host
(FastAPI, ...) reuses :mod:`wiregraph_core.classifier`, these are the tests
that pin its behavior.
"""

from wiregraph_core.classifier import (
    classify,
    effective_accepts,
    effective_alert_level,
)
from wiregraph_core.types import (
    Asset,
    Decision,
    FlowHistory,
    Policy,
    RuleHit,
    Sink,
)


STRICT = Policy(llm_mode="strict")
RELAXED = Policy(llm_mode="relaxed")


def _asset(name, sensitivity):
    return Asset(name=name, sensitivity_level=sensitivity)


def _sink(category, tier="known", accepts=None, domain="api.example.com"):
    return Sink(
        domain=domain,
        category=category,
        trust_tier=tier,
        accepts_assets=list(accepts) if accepts else [],
    )


def test_rule_hit_short_circuits_to_expected():
    decision = classify(
        _asset("email", "medium"),
        _sink("llm"),
        RuleHit(),
        STRICT,
    )
    assert decision == Decision(outcome="expected", reason="rule:allowlist")


def test_category_accepts_asset():
    decision = classify(
        _asset("email", "medium"),
        _sink("payments", tier="trusted"),
        None,
        STRICT,
    )
    assert decision.outcome == "expected"
    assert decision.reason == "category:payments_accepts_email"


def test_llm_strict_medium_is_prohibited():
    decision = classify(
        _asset("email", "medium"),
        _sink("llm"),
        None,
        STRICT,
    )
    assert decision.outcome == "prohibited"
    assert decision.reason == "policy:pii_to_llm"


def test_llm_relaxed_medium_falls_through():
    decision = classify(
        _asset("email", "medium"),
        _sink("llm"),
        None,
        RELAXED,
    )
    # Falls past LLM branch; not trusted, not new, not low → suspicious.
    assert decision.outcome == "suspicious"
    assert decision.reason.startswith("category:llm_unexpected_")


def test_llm_relaxed_high_still_prohibited():
    decision = classify(
        _asset("passport", "high"),
        _sink("llm"),
        None,
        RELAXED,
    )
    assert decision.outcome == "prohibited"
    assert decision.reason == "policy:sensitive_to_llm"


def test_unknown_sink_critical_asset_prohibited():
    decision = classify(
        _asset("credit_card", "critical"),
        _sink("unknown", tier="unknown"),
        None,
        STRICT,
    )
    assert decision.outcome == "prohibited"
    assert decision.reason == "policy:sensitive_to_unknown_sink"


def test_new_flow_short_circuit_loses_to_category_accepts():
    decision = classify(
        _asset("phone_us", "medium"),
        _sink("crm", tier="known", accepts=["phone_us"]),
        None,
        STRICT,
        FlowHistory(is_new_flow=True),
    )
    # crm accepts phone_us so we hit 'expected' first, regardless of newness.
    assert decision.outcome == "expected"


def test_new_flow_is_suspicious():
    decision = classify(
        _asset("person_name", "medium"),
        _sink("analytics"),
        None,
        STRICT,
        FlowHistory(is_new_flow=True),
    )
    assert decision.outcome == "suspicious"
    assert decision.reason == "flow:new_data_flow"


def test_history_omitted_defaults_to_no_new_flow():
    decision = classify(
        _asset("person_name", "medium"),
        _sink("analytics"),
        None,
        STRICT,
    )
    # Without history → not new → falls through to suspicious-unexpected branch.
    assert decision.outcome == "suspicious"
    assert decision.reason == "category:analytics_unexpected_person_name"


def test_trusted_sink_unexpected_asset_is_acceptable():
    decision = classify(
        _asset("ipv4", "low"),
        _sink("payments", tier="trusted", accepts=["email"]),
        None,
        STRICT,
    )
    assert decision.outcome == "acceptable"
    assert decision.reason == "trust:trusted_sink_category_payments"


def test_low_sensitivity_is_acceptable_on_known_sink():
    decision = classify(
        _asset("ipv4", "low"),
        _sink("analytics", tier="known"),
        None,
        STRICT,
    )
    assert decision.outcome == "acceptable"
    assert decision.reason == "sensitivity:low"


def test_known_sink_unexpected_asset_is_suspicious():
    decision = classify(
        _asset("email", "medium"),
        _sink("analytics", tier="known"),
        None,
        STRICT,
    )
    assert decision.outcome == "suspicious"
    assert decision.reason == "category:analytics_unexpected_email"


def test_internal_category_accepts_everything_via_wildcard():
    decision = classify(
        _asset("ssn", "critical"),
        _sink("internal", tier="trusted", accepts=["*"]),
        None,
        STRICT,
    )
    assert decision.outcome == "expected"
    assert decision.reason == "category:internal_accepts_ssn"


def test_effective_accepts_uses_category_default_when_empty():
    sink = _sink("payments", accepts=None)
    accepts = effective_accepts(sink)
    assert "email" in accepts
    assert "credit_card" in accepts


def test_effective_accepts_uses_domain_override_when_present():
    sink = _sink("payments", accepts=["email_only"])
    assert effective_accepts(sink) == ["email_only"]


# --- effective_alert_level (§4) -------------------------------------------

THRESH = (0.5, 0.9)


def test_high_confidence_prohibited_stays_prohibited():
    assert effective_alert_level("prohibited", 0.95, THRESH) == "prohibited"


def test_high_confidence_suspicious_stays_suspicious():
    assert effective_alert_level("suspicious", 0.9, THRESH) == "suspicious"


def test_low_confidence_prohibited_downgrades_to_suspicious():
    assert effective_alert_level("prohibited", 0.3, THRESH) == "suspicious"


def test_low_confidence_suspicious_downgrades_to_acceptable():
    assert effective_alert_level("suspicious", 0.49, THRESH) == "acceptable"


def test_confidence_at_low_threshold_is_not_downgraded():
    assert effective_alert_level("prohibited", 0.5, THRESH) == "prohibited"


def test_expected_and_acceptable_never_escalated_by_confidence():
    assert effective_alert_level("expected", 0.99, THRESH) == "expected"
    assert effective_alert_level("acceptable", 0.99, THRESH) == "acceptable"


def test_low_confidence_does_not_promote_acceptable_or_expected():
    assert effective_alert_level("expected", 0.1, THRESH) == "expected"
    assert effective_alert_level("acceptable", 0.1, THRESH) == "acceptable"
