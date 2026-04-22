# Wiregraph

**What sensitive user data is leaving your Django app — and where is it going?**

Most teams can't answer that. Your API returns more than you think. Your OpenAI call ships customer emails to a third party. Your Stripe webhook echoes an SSN into a log line. Static analysis won't catch it. APM won't flag it. You find out when someone files a ticket — or when legal does.

Wiregraph is a **runtime PII leak detector** that sits inside your Django app and watches the traffic you're actually serving.

## The alarm moment

A user hits `/api/v1/support/ticket/`. Your view enriches the response with an OpenAI summary. Wiregraph sees this:

```
[egress] POST api.openai.com/v1/chat/completions
  └─ EMAIL_ADDRESS  (confidence 0.99)  asset: request.body.messages[1].content
  └─ US_SSN         (confidence 0.95)  asset: request.body.messages[1].content

[response] 200 /api/v1/support/ticket/
  └─ PHONE_NUMBER   (confidence 0.90)  asset: response.body.ticket.notes
```

You didn't write code to log that. You didn't know it was happening. Now you do.

## What Wiregraph gives you

- **Runtime visibility** into every PII-bearing field crossing your app's boundary — inbound, outbound, and egress to third parties
- **An audit trail** of which endpoints leak what, broken down by tenant
- **Early warning** before a customer, auditor, or regulator finds it first
- **Evidence for compliance** — exportable PDF/JSON reports of actual observed data flows
- **Zero raw PII at rest** — detections are hashed, masked, or truncated before they ever hit your database

## 10-second quick start

```bash
pip install wiregraph
```

```python
# settings.py
import wiregraph

INSTALLED_APPS = [*INSTALLED_APPS, *wiregraph.INSTALLED_APPS]
MIDDLEWARE = wiregraph.setup(MIDDLEWARE)

WIREGRAPH = {"ENABLED": True}
```

```bash
python manage.py migrate
python manage.py wiregraph_doctor   # sanity-check your config
```

Hit any endpoint. Check `/api/v1/detection/events/`. You'll see what's leaking.

## Why not logs or APM?

| | Logs / APM | Static scanners | **Wiregraph** |
|---|---|---|---|
| Sees actual traffic | Partial | No | **Yes** |
| Detects PII semantically | No | Limited | **Yes (regex + ML)** |
| Tracks egress to third parties | No | No | **Yes** |
| Tenant-aware | No | No | **Yes** |
| Safe to store results | Depends | N/A | **Yes — never stores raw PII** |

APM tells you a request was slow. Logs tell you what you decided to log. Wiregraph tells you what your app *actually sent*.

## Security guarantee

**Wiregraph never persists raw PII.** Every detection is redacted (hash / mask / truncate, configurable) before it touches storage. The matched value exists only in memory long enough to classify and redact it. You get the signal; the sensitive bytes stay gone.

## Core features

- **Regex detection** out of the box — emails, phone numbers, SSNs, credit cards, and more
- **Custom patterns** — register project-specific detectors (internal IDs, locale formats) via `WIREGRAPH["CUSTOM_PATTERNS"]`
- **Presidio integration** (optional) — ML-powered NER for names, addresses, IBANs, and 50+ entity types; runs async via Celery so the request path stays fast
- **Egress tracking** — flags PII sent to outbound services (OpenAI, Stripe, anything you call)
- **Multi-tenant isolation** — built for SaaS
- **Configurable redaction** — hash, mask, or truncate
- **Scheduled retention purge** — via cron or Celery Beat

## Installation

```bash
pip install wiregraph              # core
pip install wiregraph[presidio]    # + ML detection (also: python -m spacy download en_core_web_lg)
pip install wiregraph[export]      # + PDF/JSON reports
pip install wiregraph[all]         # everything
```

## Full setup

1. Add Wiregraph's apps to `INSTALLED_APPS`:

    ```python
    import wiregraph
    INSTALLED_APPS = [
        # ... your apps ...
        *wiregraph.INSTALLED_APPS,
    ]
    ```

2. Install the middleware. `wiregraph.setup()` inserts both entries at the correct positions (idempotent):

    ```python
    MIDDLEWARE = wiregraph.setup([
        # ... your existing middleware ...
        "django.contrib.auth.middleware.AuthenticationMiddleware",
    ])
    ```

    Wiring manually? Keep `JWTAuthMiddleware` before `PIIDetectionMiddleware`, both after `AuthenticationMiddleware`.

3. Configure. Only `ENABLED` is required; every other key has a default.

    ```python
    WIREGRAPH = {"ENABLED": True}
    ```

    See [docs/settings.md](docs/settings.md) for all keys.

    > **Admin auto-exclusion.** Wiregraph skips your Django admin URL prefix by default (`AUTO_EXCLUDE_ADMIN=True`) — otherwise the `DataEvent` list view would re-detect the PII it displays on every refresh. Set to `False` to opt out.

4. Run migrations:

    ```bash
    python manage.py migrate
    ```

### Custom tenant resolution

By default Wiregraph walks `request.user.tenant_memberships`. If your project stores tenancy differently (FK, subdomain, gateway header), point `TENANT_RESOLVER` at your own callable:

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

## Extending detection

### Custom regex patterns

```python
WIREGRAPH = {
    "ENABLED": True,
    "CUSTOM_PATTERNS": [
        {"name": "emp_id", "regex": r"\bEMP-\d{6}\b", "confidence": 0.9},
        {"name": "phone_uk", "regex": r"\+44\s?\d{2,4}\s?\d{3,4}\s?\d{3,4}", "flags": "i"},
    ],
}
```

Each entry takes `name`, `regex`, optional `confidence` (default `0.75`), optional `flags` (string of `imsxa`). Invalid specs fail loudly at startup.

### Presidio (deep NLP)

```python
WIREGRAPH = {
    "ENABLED": True,
    "ENABLE_PRESIDIO": True,
}
```

Requires the `presidio` extra, a spaCy language model, and a running Celery worker — see [Installing Presidio](docs/SETUP_GUIDE.md#installing-presidio). Presidio matches that overlap a regex match on the same asset are deduped (regex wins on precision).

## Scheduled retention purge

Delete events older than `DATA_RETENTION_DAYS`.

Via cron / systemd:

```bash
python manage.py wiregraph_purge [--dry-run] [--batch-size N]
```

Via Celery Beat:

```python
import wiregraph.celery as wg_celery

CELERY_BEAT_SCHEDULE = {
    **wg_celery.schedule(hour=3, minute=0),
    # ... your other scheduled tasks ...
}
```

Other management commands:

```bash
python manage.py wiregraph_doctor   # verify configuration
python manage.py wiregraph_init --settings-file config/settings.py   # scaffold config block
```

## API

All endpoints are versioned under `/api/v1/` and require a JWT `Bearer` token (obtain via `/api/v1/auth/token/`). OpenAPI schema at `/api/v1/schema/`, Swagger UI at `/api/v1/schema/docs/`.

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
