from django.conf import settings

DEFAULTS = {
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
}


def get_config(key):
    user_conf = getattr(settings, "WIREGRAPH", {})
    return user_conf.get(key, DEFAULTS[key])


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
