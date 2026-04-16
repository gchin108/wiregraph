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

1. Add the Wiregraph apps to `INSTALLED_APPS` — spread the bundled list:

```python
import wiregraph

INSTALLED_APPS = [
    # ... your apps ...
    *wiregraph.INSTALLED_APPS,
]
```

2. Install the middleware with one call — `wiregraph.setup()` inserts both entries at the correct positions (idempotent):

```python
import wiregraph

MIDDLEWARE = wiregraph.setup([
    # ... your existing middleware ...
    "django.contrib.auth.middleware.AuthenticationMiddleware",
])
```

Prefer wiring it manually? Keep `JWTAuthMiddleware` before `PIIDetectionMiddleware`, both after `AuthenticationMiddleware`.

3. Configure Wiregraph in your settings. Only `ENABLED` is required — every other key has a sensible default:

```python
WIREGRAPH = {
    "ENABLED": True,
}
```

See [docs/settings.md](docs/settings.md) for all available keys, types, and defaults.

**Custom tenant resolution.** By default Wiregraph walks `request.user.tenant_memberships` to find the active tenant. If your project stores tenancy differently (FK on the user, subdomain, gateway header, etc.), point `WIREGRAPH["TENANT_RESOLVER"]` at your own callable:

```python
# myapp/tenancy.py
def resolve(request):
    return getattr(request.user, "active_tenant", None)

# settings.py
WIREGRAPH = {
    "ENABLED": True,
    "TENANT_RESOLVER": "myapp.tenancy.resolve",
}
```

4. Run migrations:

```bash
python manage.py migrate
```

## Scheduled retention purge

Delete events older than `DATA_RETENTION_DAYS` on a schedule.

Via cron / systemd:

```bash
python manage.py wiregraph_purge [--dry-run] [--batch-size N]
```

Check your configuration any time with the built-in doctor:

```bash
python manage.py wiregraph_doctor
```

Or scaffold a minimal config block into an existing settings file:

```bash
python manage.py wiregraph_init --settings-file config/settings.py
```

Via Celery Beat:

```python
import wiregraph.celery as wg_celery

CELERY_BEAT_SCHEDULE = {
    **wg_celery.schedule(hour=3, minute=0),
    # ... your other scheduled tasks ...
}
```

## API

All endpoints are versioned under `/api/v1/` and require a JWT `Bearer` token (obtain one via `/api/v1/auth/token/`). The OpenAPI schema is served at `/api/v1/schema/` and Swagger UI at `/api/v1/schema/docs/`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/token/` | Obtain access + refresh token (throttled 5/min) |
| POST | `/api/v1/auth/token/refresh/` | Rotate refresh token (throttled 5/min) |
| GET | `/api/v1/detection/events/` | List detection events (filter: `direction`, `data_asset`, `endpoint`, `timestamp__gte`, `timestamp__lte`) |
| GET | `/api/v1/detection/events/{id}/` | Retrieve a single event |
| GET | `/api/v1/detection/assets/` | List PII categories seen in traffic |
| GET | `/api/v1/detection/stats/summary/` | Dashboard counts by direction and asset |

## Requirements

- Python >= 3.10
- Django >= 5.0
- Celery + Redis (for async detection)
- PostgreSQL (recommended)

## License

MIT
