"""Tests for ``wiregraph_apps.sinks.resolve_sink`` override precedence."""

import pytest

from wiregraph_apps.sinks import (
    ASSET_SENSITIVITY,
    CATEGORY_DEFAULTS,
    resolve_sink,
    sensitivity_for,
)


def test_builtin_catalog_stripe_payments_trusted():
    info = resolve_sink("api.stripe.com")
    assert info.category == "payments"
    assert info.trust_tier == "trusted"
    assert "email" in info.accepts_assets
    assert "credit_card" in info.accepts_assets


def test_builtin_catalog_openai_llm_known_empty_accepts():
    info = resolve_sink("api.openai.com")
    assert info.category == "llm"
    assert info.trust_tier == "known"
    assert info.accepts_assets == []


def test_fallback_unknown_host():
    info = resolve_sink("weirdhost.example")
    assert info.category == "unknown"
    assert info.trust_tier == "unknown"
    assert info.accepts_assets == []


def test_settings_override_beats_builtin(settings):
    settings.WIREGRAPH = {
        "SINK_OVERRIDES": {
            "openai.com": {
                "category": "llm",
                "trust_tier": "trusted",  # override tier
                "accepts_assets": ["prompt_id"],
                "display_name": "Private OpenAI",
            }
        }
    }
    info = resolve_sink("api.openai.com")
    assert info.trust_tier == "trusted"
    assert info.accepts_assets == ["prompt_id"]
    assert info.display_name == "Private OpenAI"


@pytest.mark.django_db
def test_db_override_beats_settings_and_builtin(settings):
    from tests.fixtures.factories import TenantFactory
    from wiregraph_apps.egress.models import SinkCatalogOverride

    tenant = TenantFactory()
    settings.WIREGRAPH = {
        "SINK_OVERRIDES": {
            "stripe.com": {
                "category": "payments",
                "trust_tier": "known",
                "accepts_assets": ["email"],
                "display_name": "Settings Stripe",
            }
        }
    }
    SinkCatalogOverride.objects.create(
        tenant=tenant,
        domain_suffix="stripe.com",
        category="payments",
        trust_tier="trusted",
        accepts_assets=["tenant_only_field"],
        display_name="DB Stripe",
    )
    info = resolve_sink("api.stripe.com", tenant=tenant)
    assert info.display_name == "DB Stripe"
    assert info.accepts_assets == ["tenant_only_field"]


def test_longest_suffix_wins(settings):
    settings.WIREGRAPH = {
        "SINK_OVERRIDES": {
            "example.com": {
                "category": "analytics",
                "trust_tier": "known",
                "accepts_assets": [],
            },
            "api.example.com": {
                "category": "llm",
                "trust_tier": "known",
                "accepts_assets": [],
            },
        }
    }
    info = resolve_sink("api.example.com")
    assert info.category == "llm"


def test_category_default_applied_when_accepts_is_none(settings):
    settings.WIREGRAPH = {
        "SINK_OVERRIDES": {
            "pay.example": {
                "category": "payments",
                "trust_tier": "trusted",
                # no accepts_assets → should pick up category default
            }
        }
    }
    info = resolve_sink("pay.example")
    assert set(info.accepts_assets) == set(CATEGORY_DEFAULTS["payments"])


def test_sensitivity_for_known_and_unknown():
    assert sensitivity_for("credit_card") == "critical"
    assert sensitivity_for("email") == "medium"
    assert sensitivity_for("ipv4") == "low"
    assert sensitivity_for("made_up_asset") == "medium"
    for asset in ASSET_SENSITIVITY:
        assert sensitivity_for(asset) in {"low", "medium", "high", "critical"}
