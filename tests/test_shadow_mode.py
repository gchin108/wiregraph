"""Unit tests for Phase 2 shadow-mode helper (no DB).

Exercises :func:`apply_shadow_decision` against a lightweight event stand-in so
the mapping outcome+confidence → shadow_alert_level is covered without Django
fixtures. Integration tests that assert call-site wiring live in the
middleware/egress-interceptor test modules.
"""

from types import SimpleNamespace

from django.test import override_settings

from wiregraph_apps.detection.classifier import apply_shadow_decision


def _event(outcome, confidence, reason="rule:allowlist"):
    return SimpleNamespace(
        pk=1,
        tenant_id=1,
        outcome=outcome,
        confidence=confidence,
        decision_reason=reason,
        shadow_alert_level="",
        data_asset=SimpleNamespace(name="email"),
        external_service=SimpleNamespace(domain="api.example.com"),
    )


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_shadow_sets_level_from_outcome_and_confidence():
    event = _event("prohibited", 0.95)
    level = apply_shadow_decision(event)
    assert level == "prohibited"
    assert event.shadow_alert_level == "prohibited"


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_shadow_downgrades_low_confidence_prohibited():
    event = _event("prohibited", 0.3)
    assert apply_shadow_decision(event) == "suspicious"
    assert event.shadow_alert_level == "suspicious"


@override_settings(WIREGRAPH={"SHADOW_MODE": True, "CONFIDENCE_LOW": 0.5, "CONFIDENCE_HIGH": 0.9})
def test_shadow_downgrades_low_confidence_suspicious():
    event = _event("suspicious", 0.2)
    assert apply_shadow_decision(event) == "acceptable"


@override_settings(WIREGRAPH={"SHADOW_MODE": False})
def test_shadow_noop_when_disabled():
    event = _event("prohibited", 0.95)
    assert apply_shadow_decision(event) == ""
    assert event.shadow_alert_level == ""


@override_settings(WIREGRAPH={"SHADOW_MODE": True})
def test_shadow_uses_default_thresholds():
    # No explicit thresholds set — falls back to DEFAULTS (0.5 / 0.9).
    event = _event("suspicious", 0.95)
    assert apply_shadow_decision(event) == "suspicious"
