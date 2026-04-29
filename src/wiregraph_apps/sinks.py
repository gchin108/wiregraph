"""Built-in sink catalog + resolver.

A **sink** is any outbound destination Wiregraph sees in traffic
(`ExternalService` row). The catalog lets us classify a new sink the moment
it's observed — `api.stripe.com` is `payments/trusted`, `api.openai.com` is
`llm/known` — so classification has meaningful inputs without per-tenant setup.

Resolution order on first sight of a host:
    1. Tenant override (DB: ``SinkCatalogOverride``)
    2. ``WIREGRAPH["SINK_OVERRIDES"]`` (settings)
    3. Built-in catalog below
    4. Fallback (``unknown`` category / tier, no accepts)

Entries are matched by longest ``domain_suffix`` wins; an entry matches a host
if ``host == suffix`` or ``host`` ends with ``"." + suffix``.

Asset sensitivity defaults also live here (used when auto-creating a
``DataAsset`` so ``sensitivity_level`` is set from a known mapping instead of
defaulting to ``medium``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Category defaults — per proposal §2 "Category-level accepts_assets defaults".
# A per-domain ``accepts_assets`` on a catalog entry overrides these.
# ---------------------------------------------------------------------------
CATEGORY_DEFAULTS: dict[str, list[str]] = {
    "payments": ["email", "person_name", "address", "phone_us", "credit_card"],
    "email_provider": ["email", "person_name"],
    "crm": ["email", "person_name", "phone_us", "address"],
    "auth": ["email", "person_name"],
    "sms": ["phone_us", "person_name"],
    "analytics": [],
    "llm": [],
    "storage": [],
    "cdn": [],
    "logging": [],
    "internal": ["*"],
    "unknown": [],
}


# ---------------------------------------------------------------------------
# Built-in catalog. Keyed by ``domain_suffix``. Update via library release.
# ``accepts_assets=None`` means "use category default".
# ---------------------------------------------------------------------------
BUILTIN_CATALOG: dict[str, dict[str, Any]] = {
    # Payments
    "stripe.com": {
        "category": "payments",
        "trust_tier": "trusted",
        "accepts_assets": None,  # ← None = use category default
        "display_name": "Stripe",
    },
    # LLMs
    "api.openai.com": {
        "category": "llm",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "OpenAI",
    },
    "api.anthropic.com": {
        "category": "llm",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Anthropic",
    },
    "generativelanguage.googleapis.com": {
        "category": "llm",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Google Generative Language",
    },
    "bedrock-runtime.amazonaws.com": {
        "category": "llm",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "AWS Bedrock",
    },
    # SMS / voice
    "twilio.com": {
        "category": "sms",
        "trust_tier": "trusted",
        "accepts_assets": None,
        "display_name": "Twilio",
    },
    # Email providers
    "sendgrid.com": {
        "category": "email_provider",
        "trust_tier": "trusted",
        "accepts_assets": None,
        "display_name": "SendGrid",
    },
    "mailgun.org": {
        "category": "email_provider",
        "trust_tier": "trusted",
        "accepts_assets": None,
        "display_name": "Mailgun",
    },
    # Analytics
    "segment.io": {
        "category": "analytics",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Segment",
    },
    "mixpanel.com": {
        "category": "analytics",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Mixpanel",
    },
    "amplitude.com": {
        "category": "analytics",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Amplitude",
    },
    # Storage
    "s3.amazonaws.com": {
        "category": "storage",
        "trust_tier": "known",
        "accepts_assets": [],
        "display_name": "Amazon S3",
    },
    # Auth
    "auth0.com": {
        "category": "auth",
        "trust_tier": "trusted",
        "accepts_assets": None,
        "display_name": "Auth0",
    },
    "clerk.dev": {
        "category": "auth",
        "trust_tier": "trusted",
        "accepts_assets": None,
        "display_name": "Clerk",
    },
}


# ---------------------------------------------------------------------------
# Asset sensitivity mapping. Used when auto-creating a DataAsset.
# Unlisted assets fall back to "medium".
# ---------------------------------------------------------------------------
ASSET_SENSITIVITY: dict[str, str] = {
    # critical
    "credit_card": "critical",
    "ssn": "critical",
    # high
    "passport": "high",
    "driver_license": "high",
    "medical_license": "high",
    "iban": "high",
    # medium
    "email": "medium",
    "phone_us": "medium",
    "person_name": "medium",
    "address": "medium",
    # low
    "ipv4": "low",
    "ipv6": "low",
    "date_time": "low",
}


def sensitivity_for(asset_name: str) -> str:
    return ASSET_SENSITIVITY.get(asset_name, "medium")


@dataclass(frozen=True)
class SinkInfo:
    category: str
    trust_tier: str
    accepts_assets: list[str]
    display_name: str


_UNKNOWN = SinkInfo(
    category="unknown",
    trust_tier="unknown",
    accepts_assets=[],
    display_name="",
)


def _match_catalog(host: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Return the longest-suffix-matching entry, or None."""
    host = host.lower()
    best: tuple[int, dict[str, Any]] | None = None
    for suffix, entry in catalog.items():
        s = suffix.lower()
        if host == s or host.endswith("." + s):
            if best is None or len(s) > best[0]:
                best = (len(s), entry)
    return best[1] if best else None


def _entry_to_info(entry: dict[str, Any], host: str) -> SinkInfo:
    category = entry.get("category", "unknown")
    trust_tier = entry.get("trust_tier", "unknown")
    raw_accepts = entry.get("accepts_assets", None)
    if raw_accepts is None:
        accepts = list(CATEGORY_DEFAULTS.get(category, []))
    else:
        accepts = list(raw_accepts)
    return SinkInfo(
        category=category,
        trust_tier=trust_tier,
        accepts_assets=accepts,
        display_name=entry.get("display_name", "") or host,
    )


def resolve_sink(host: str, tenant=None) -> SinkInfo:
    """Resolve a host to a ``SinkInfo`` using the proposal's precedence.

    DB override → settings override → built-in → fallback ``unknown``.
    DB lookup happens lazily and only when ``tenant`` is provided.
    """
    if not host:
        return _UNKNOWN

    # 1. Tenant override in DB
    if tenant is not None:
        try:
            from wiregraph_apps.egress.models import SinkCatalogOverride

            overrides = {
                row.domain_suffix: {
                    "category": row.category,
                    "trust_tier": row.trust_tier,
                    "accepts_assets": row.accepts_assets or None,
                    "display_name": row.display_name,
                }
                for row in SinkCatalogOverride.objects.filter(tenant=tenant)
            }
        except Exception:  # pragma: no cover — model may not yet be migrated in tests
            overrides = {}
        entry = _match_catalog(host, overrides)
        if entry is not None:
            return _entry_to_info(entry, host)

    # 2. WIREGRAPH["SINK_OVERRIDES"]
    from wiregraph_apps.common.conf import get_sink_overrides

    settings_overrides = get_sink_overrides() or {}
    entry = _match_catalog(host, settings_overrides)
    if entry is not None:
        return _entry_to_info(entry, host)

    # 3. Built-in catalog
    entry = _match_catalog(host, BUILTIN_CATALOG)
    if entry is not None:
        return _entry_to_info(entry, host)

    # 4. Fallback
    return SinkInfo(
        category="unknown",
        trust_tier="unknown",
        accepts_assets=[],
        display_name=host,
    )
