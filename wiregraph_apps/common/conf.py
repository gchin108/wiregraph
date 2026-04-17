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
    "TENANT_RESOLVER": "wiregraph.resolvers.default",
    "TENANT_MODEL": "wiregraph_tenants.Tenant",
    "DISABLE_BUILTIN_ALERTS": False,
    "ADMIN_SITE": "django.contrib.admin.site",
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
    TENANT_RESOLVER: str
    TENANT_MODEL: str
    DISABLE_BUILTIN_ALERTS: bool
    ADMIN_SITE: str


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
    return list(get_config("EXCLUDED_PATHS"))


def get_redact_strategy() -> str:
    return str(get_config("REDACT_STRATEGY"))


def get_allowlisted_fields() -> list[str]:
    return list(get_config("ALLOWLISTED_FIELDS"))
