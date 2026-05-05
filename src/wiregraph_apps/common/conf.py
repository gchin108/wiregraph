from typing import TypedDict

from django.conf import settings

DEFAULTS = {
    "ENABLED": False,
    "ENABLE_PRESIDIO": False,
    "ENABLE_EGRESS_TRACKING": False,
    "DISABLE_EGRESS_PATCHING": False,
    "DATA_RETENTION_DAYS": 90,
    "REDACT_STRATEGY": "hash",
    "ALERT_WEBHOOK_URL": None,
    "ALLOWLISTED_FIELDS": [],
    "SAMPLING_RATE": 1.0,
    "MAX_BODY_SIZE": 1_048_576,
    "EXCLUDED_PATHS": [],
    "AUTO_EXCLUDE_ADMIN": True,
    "AUTO_EXCLUDE_API": True,
    "TENANT_RESOLVER": "wiregraph.resolvers.default",
    "TENANT_MODEL": "wiregraph_tenants.Tenant",
    "DISABLE_BUILTIN_ALERTS": False,
    "ADMIN_SITE": "django.contrib.admin.site",
    "CUSTOM_PATTERNS": [],
    "LLM_POLICY": "strict",
    "SINK_OVERRIDES": {},
    "CONFIDENCE_LOW": 0.5,
    "CONFIDENCE_HIGH": 0.9,
    "SHADOW_MODE": False,
    "PAGER_WEBHOOK_URL": None,
    "DEDUP_WINDOW_PROHIBITED_SECONDS": 300,
    "DEDUP_WINDOW_SUSPICIOUS_SECONDS": 3600,
    "ESCALATION_SUSPICIOUS_COUNT": 10,
    "ESCALATION_WINDOW_SECONDS": 86400,
}


class WiregraphSettings(TypedDict, total=False):
    ENABLED: bool
    ENABLE_PRESIDIO: bool
    ENABLE_EGRESS_TRACKING: bool
    DISABLE_EGRESS_PATCHING: bool
    DATA_RETENTION_DAYS: int
    REDACT_STRATEGY: str
    ALERT_WEBHOOK_URL: str | None
    ALLOWLISTED_FIELDS: list[str]
    SAMPLING_RATE: float
    MAX_BODY_SIZE: int
    EXCLUDED_PATHS: list[str]
    AUTO_EXCLUDE_ADMIN: bool
    AUTO_EXCLUDE_API: bool
    TENANT_RESOLVER: str
    TENANT_MODEL: str
    DISABLE_BUILTIN_ALERTS: bool
    ADMIN_SITE: str
    CUSTOM_PATTERNS: list[dict]
    LLM_POLICY: str
    SINK_OVERRIDES: dict
    CONFIDENCE_LOW: float
    CONFIDENCE_HIGH: float
    SHADOW_MODE: bool
    PAGER_WEBHOOK_URL: str | None
    DEDUP_WINDOW_PROHIBITED_SECONDS: int
    DEDUP_WINDOW_SUSPICIOUS_SECONDS: int
    ESCALATION_SUSPICIOUS_COUNT: int
    ESCALATION_WINDOW_SECONDS: int


def get_config(key):
    user_conf = getattr(settings, "WIREGRAPH", {})
    return user_conf.get(key, DEFAULTS[key])


def is_enabled() -> bool:
    return bool(get_config("ENABLED"))


def get_sampling_rate() -> float:
    return float(get_config("SAMPLING_RATE"))


def get_max_body_size() -> int:
    return int(get_config("MAX_BODY_SIZE"))


def get_excluded_paths() -> list[str]:
    paths = list(get_config("EXCLUDED_PATHS"))
    if get_config("AUTO_EXCLUDE_ADMIN"):
        admin_prefix = _resolve_admin_prefix()
        if admin_prefix and admin_prefix not in paths:
            paths.append(admin_prefix)
    if get_config("AUTO_EXCLUDE_API"):
        api_prefix = _resolve_api_prefix()
        if api_prefix and api_prefix not in paths:
            paths.append(api_prefix)
    return paths


def _resolve_admin_prefix() -> str | None:
    """Return the mounted Django admin URL prefix, or None if unavailable.

    Scanning the admin creates a feedback loop: wiregraph's own DataEvent list
    view renders detected PII, which the middleware would then re-detect.
    """
    try:
        from django.urls import reverse
        return reverse("admin:index")
    except Exception:
        return None


def _resolve_api_prefix() -> str | None:
    """Return the mounted ``wiregraph.api_urls`` prefix, or None if unmounted.

    Without this guard the detection middleware re-scans the JSON API's own
    responses — ``DataEventSerializer`` emits redacted PII snippets that the
    regex/presidio scanner re-flags, generating fresh ``DataEvent`` rows on
    every dashboard poll.
    """
    try:
        from django.urls import NoReverseMatch, reverse
    except Exception:
        return None
    try:
        return reverse("wiregraph-api-root")
    except NoReverseMatch:
        return None
    except Exception:
        return None


def get_redact_strategy() -> str:
    return str(get_config("REDACT_STRATEGY"))


def get_allowlisted_fields() -> list[str]:
    return list(get_config("ALLOWLISTED_FIELDS"))


def get_custom_patterns() -> list[dict]:
    return list(get_config("CUSTOM_PATTERNS"))


def get_llm_policy() -> str:
    return str(get_config("LLM_POLICY"))


def get_sink_overrides() -> dict:
    return dict(get_config("SINK_OVERRIDES"))


def get_confidence_thresholds() -> tuple[float, float]:
    return float(get_config("CONFIDENCE_LOW")), float(get_config("CONFIDENCE_HIGH"))


def is_shadow_mode() -> bool:
    return bool(get_config("SHADOW_MODE"))


def get_dedup_windows() -> tuple[int, int]:
    """Return ``(prohibited_seconds, suspicious_seconds)`` dedup windows."""
    return (
        int(get_config("DEDUP_WINDOW_PROHIBITED_SECONDS")),
        int(get_config("DEDUP_WINDOW_SUSPICIOUS_SECONDS")),
    )


def get_escalation_config() -> tuple[int, int]:
    """Return ``(count_threshold, window_seconds)`` for suspicious→prohibited escalation."""
    return (
        int(get_config("ESCALATION_SUSPICIOUS_COUNT")),
        int(get_config("ESCALATION_WINDOW_SECONDS")),
    )
