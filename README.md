# Wiregraph

Runtime PII leak detector for Django. Wiregraph finds personal data leaking from your API responses and third-party calls.

## What it does

Wiregraph sits inside your Django application and monitors HTTP traffic for personally identifiable information (PII). It detects PII in both **inbound/outbound API responses** and **egress traffic to third-party services**, logging every occurrence without ever storing raw PII.

- **Regex-based detection** out of the box -- catches emails, phone numbers, SSNs, credit cards, and more
- **Presidio integration** (optional) for ML-powered entity recognition
- **Egress tracking** -- monitors outbound calls to external services (e.g., OpenAI, Stripe) and flags PII sent to them
- **Multi-tenant** -- built for SaaS with full tenant isolation
- **Compliance reporting** -- export PDF or JSON reports of PII data flows
- **Configurable redaction** -- hash, mask, or truncate detected PII in event logs
- **Async processing** -- offloads detection to Celery workers for minimal request latency

## Installation

```bash
pip install wiregraph
```

With optional extras:

```bash
# Presidio ML-based detection
pip install wiregraph[presidio]

# PDF/JSON export support
pip install wiregraph[export]

# Everything
pip install wiregraph[all]
```

## Quick start

1. Add the Wiregraph apps to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "core_apps.common",
    "core_apps.tenants",
    "core_apps.detection",
    "core_apps.egress",
    "core_apps.reporting",
]
```

2. Add the detection middleware:

```python
MIDDLEWARE = [
    # ...
    "core_apps.detection.middleware.PIIDetectionMiddleware",
]
```

3. Configure Wiregraph in your settings:

```python
WIREGRAPH = {
    "ENABLE_PRESIDIO": False,          # Use ML-based detection (requires presidio extra)
    "ENABLE_EGRESS_TRACKING": False,   # Monitor outbound third-party calls
    "DATA_RETENTION_DAYS": 90,         # How long to keep detection events
    "REDACT_STRATEGY": "hash",         # "hash", "mask", or "truncate"
    "SAMPLING_RATE": 1.0,              # 1.0 = scan every request, 0.1 = 10%
    "MAX_BODY_SIZE": 1_048_576,        # Skip bodies larger than 1MB
    "EXCLUDED_PATHS": [],              # Paths to skip (e.g., ["/health/"])
    "ALLOWLISTED_FIELDS": [],          # Field names to ignore
    "ALERT_WEBHOOK_URL": None,         # POST alerts to this URL
}
```

4. Run migrations:

```bash
python manage.py migrate
```

## Requirements

- Python >= 3.10
- Django >= 5.0
- Celery + Redis (for async detection)
- PostgreSQL (recommended)

## License

MIT
