"""Unit tests for the pure classifier function.

No DB or Django fixtures — the classifier only takes dataclasses.
"""

from wiregraph_apps.detection.classifier import (
    AssetSpec,
    Policy,
    RuleHit,
    ServiceSpec,
    classify,
    effective_accepts,
    effective_alert_level,
)


STRICT = Policy(llm_mode="strict")
RELAXED = Policy(llm_mode="relaxed")


def _asset(name, sensitivity):
    return AssetSpec(name=name, sensitivity_level=sensitivity)


def _service(category, tier="known", accepts=None, domain="api.example.com"):
    return ServiceSpec(
        domain=domain,
        category=category,
        trust_tier=tier,
        accepts_assets=list(accepts) if accepts else [],
    )


def test_rule_hit_short_circuits_to_expected():
    outcome, reason = classify(
        _asset("email", "medium"),
        _service("llm"),
        RuleHit(source="manual"),
        STRICT,
    )
    assert outcome == "expected"
    assert reason == "rule:allowlist"


def test_category_accepts_asset():
    outcome, reason = classify(
        _asset("email", "medium"),
        _service("payments", tier="trusted"),
        None,
        STRICT,
    )
    assert outcome == "expected"
    assert reason == "category:payments_accepts_email"


def test_llm_strict_medium_is_prohibited():
    outcome, reason = classify(
        _asset("email", "medium"),
        _service("llm"),
        None,
        STRICT,
    )
    assert outcome == "prohibited"
    assert reason == "policy:pii_to_llm"


def test_llm_relaxed_medium_falls_through_to_new_flow_or_category_miss():
    outcome, reason = classify(
        _asset("email", "medium"),
        _service("llm"),
        None,
        RELAXED,
    )
    # Falls past LLM branch; not trusted, not new, not low → suspicious.
    assert outcome == "suspicious"
    assert reason.startswith("category:llm_unexpected_")


def test_llm_relaxed_high_still_prohibited():
    outcome, reason = classify(
        _asset("passport", "high"),
        _service("llm"),
        None,
        RELAXED,
    )
    assert outcome == "prohibited"
    assert reason == "policy:sensitive_to_llm"


def test_unknown_sink_critical_asset_prohibited():
    outcome, reason = classify(
        _asset("credit_card", "critical"),
        _service("unknown", tier="unknown"),
        None,
        STRICT,
    )
    assert outcome == "prohibited"
    assert reason == "policy:sensitive_to_unknown_sink"


def test_new_flow_is_suspicious():
    outcome, reason = classify(
        _asset("phone_us", "medium"),
        _service("crm", tier="known", accepts=["phone_us"]),
        None,
        STRICT,
        is_new_flow=True,
    )
    # crm accepts phone_us so we hit 'expected' first, regardless of newness.
    assert outcome == "expected"

    outcome, reason = classify(
        _asset("person_name", "medium"),
        _service("analytics"),
        None,
        STRICT,
        is_new_flow=True,
    )
    assert outcome == "suspicious"
    assert reason == "flow:new_data_flow"


def test_trusted_sink_unexpected_asset_is_acceptable():
    # Trusted payments sink but the asset isn't on the accept list and isn't on
    # the critical ladder — should be acceptable.
    outcome, reason = classify(
        _asset("ipv4", "low"),
        _service("payments", tier="trusted", accepts=["email"]),
        None,
        STRICT,
    )
    # low sensitivity path is checked after trusted — trusted branches first.
    assert outcome == "acceptable"
    assert reason == "trust:trusted_sink_category_payments"


def test_low_sensitivity_is_acceptable_on_known_sink():
    outcome, reason = classify(
        _asset("ipv4", "low"),
        _service("analytics", tier="known"),
        None,
        STRICT,
    )
    assert outcome == "acceptable"
    assert reason == "sensitivity:low"


def test_known_sink_unexpected_asset_is_suspicious():
    outcome, reason = classify(
        _asset("email", "medium"),
        _service("analytics", tier="known"),
        None,
        STRICT,
    )
    assert outcome == "suspicious"
    assert reason == "category:analytics_unexpected_email"


def test_effective_accepts_uses_category_default_when_empty():
    s = _service("payments", accepts=None)
    accepts = effective_accepts(s)
    assert "email" in accepts
    assert "credit_card" in accepts


def test_effective_accepts_uses_domain_override_when_present():
    s = _service("payments", accepts=["email_only"])
    assert effective_accepts(s) == ["email_only"]


def test_internal_category_accepts_everything_via_wildcard():
    outcome, reason = classify(
        _asset("ssn", "critical"),
        _service("internal", tier="trusted", accepts=["*"]),
        None,
        STRICT,
    )
    assert outcome == "expected"
    assert reason == "category:internal_accepts_ssn"


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
