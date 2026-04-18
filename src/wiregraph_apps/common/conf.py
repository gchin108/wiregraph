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
    "TENANT_RESOLVER": "wiregraph.resolvers.default",
    "TENANT_MODEL": "wiregraph_tenants.Tenant",
    "DISABLE_BUILTIN_ALERTS": False,
    "ADMIN_SITE": "django.contrib.admin.site",
    "CUSTOM_PATTERNS": [],
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
    TENANT_RESOLVER: str
    TENANT_MODEL: str
    DISABLE_BUILTIN_ALERTS: bool
    ADMIN_SITE: str
    CUSTOM_PATTERNS: list[dict]


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


def get_redact_strategy() -> str:
    return str(get_config("REDACT_STRATEGY"))


def get_allowlisted_fields() -> list[str]:
    return list(get_config("ALLOWLISTED_FIELDS"))


def get_custom_patterns() -> list[dict]:
    return list(get_config("CUSTOM_PATTERNS"))
