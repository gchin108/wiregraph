# Wiregraph

**What sensitive user data is leaving your Django app — and where is it going?**

Most teams can't answer that. Your view returns more than you think. Your OpenAI call ships customer emails to a third party. Your Stripe webhook echoes an SSN into a log line. Static analysis won't catch it. APM won't flag it.

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

## What you get

- **Runtime visibility** into every PII-bearing field crossing your app's boundary — inbound, outbound, egress
- **Audit trail** of which endpoints leak what, by tenant
- **Compliance evidence** — exportable PDF/JSON reports of observed flows
- **Zero raw PII at rest** — detections are hashed, masked, or truncated before storage

APM tells you a request was slow. Logs tell you what you decided to log. Wiregraph tells you what your app *actually sent*.

## Quick start

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
python manage.py wiregraph_doctor   # sanity-check config

# attach your admin user to a tenant so events get attributed
python manage.py shell -c "from django.contrib.auth import get_user_model; from wiregraph_apps.tenants.models import Tenant, TenantMembership; u = get_user_model().objects.filter(is_superuser=True).first(); t, _ = Tenant.objects.get_or_create(name='Demo Co', defaults={'slug': 'demo'}); TenantMembership.objects.get_or_create(user=u, tenant=t)"
```

Hit any endpoint, then open `/admin/wiregraph/dashboard/` to see the flow graph.
(For the JSON API at `/api/v1/`, install `wiregraph[drf]` — see below.)

> Wiregraph skips the Django admin URL prefix by default — otherwise the `DataEvent` admin would re-detect its own contents on refresh. Override with `AUTO_EXCLUDE_ADMIN=False`.

## Install extras

Wiregraph ships in slices so you only pull in what you need.

| Install line | What you get |
|---|---|
| `pip install wiregraph` | Core middleware + bundled admin dashboard at `/admin/wiregraph/dashboard/`. No DRF. |
| `pip install wiregraph[drf]` | Adds the JSON API at `/api/v1/` (viewsets, JWT auth, OpenAPI schema). Required by the React `wiregraph-dashboard` consumer. |
| `pip install wiregraph[presidio]` | ML-based detection. Also run `python -m spacy download en_core_web_lg`. |
| `pip install wiregraph[export]` | PDF/JSON compliance reports. |
| `pip install wiregraph[postgres]` | `psycopg[binary]` for Postgres backends. |
| `pip install wiregraph[all]` | Everything above plus dev tooling. |

If you skip `[drf]`, the `/api/v1/` routes are not registered — the admin dashboard still works.

## Security guarantee

**Wiregraph never persists raw PII.** Every detection is redacted (hash / mask / truncate, configurable) before it touches storage. The matched value lives in memory only long enough to classify and redact.

## Detection

Regex out of the box: emails, phones, SSNs, credit cards, and more. Add your own:

```python
WIREGRAPH = {
    "ENABLED": True,
    "CUSTOM_PATTERNS": [
        {"name": "emp_id", "regex": r"\bEMP-\d{6}\b", "confidence": 0.9},
    ],
}
```

Optional Presidio (ML NER for names, addresses, IBANs, 50+ entity types) runs async via Celery so the request path stays fast:

```python
WIREGRAPH = {"ENABLED": True, "ENABLE_PRESIDIO": True}
```

See [Installing Presidio](docs/SETUP_GUIDE.md#installing-presidio). Presidio matches that overlap a regex hit on the same asset are deduped (regex wins).

## Classification

Not every PII hit is a leak. An email to `api.stripe.com` is the product working; the same email to `api.openai.com` is an incident. Wiregraph classifies every `DataEvent` on **what × where × policy** and writes the verdict to `DataEvent.outcome`:

| Outcome | Meaning |
|---|---|
| `expected` | Asset flowed to a sink that accepts it (Stripe ← email) |
| `acceptable` | Trusted sink, asset not on its accept-list but not dangerous |
| `suspicious` | Unknown sink, new flow, or known sink receiving an unexpected asset |
| `prohibited` | Sensitive asset to a sink that should never receive it |

A built-in catalog (~15 vendors: Stripe, OpenAI, Anthropic, Bedrock, Twilio, SendGrid, Segment, S3, Auth0, …) means a fresh install gets meaningful outcomes with zero setup. Override per-host via `SINK_OVERRIDES` (settings) or `SinkCatalogOverride` (DB, tenant-scoped). LLM strictness is tunable: `LLM_POLICY = "strict"` (default — medium+ PII to LLM is `prohibited`) or `"relaxed"`.

## Tenant resolution

By default Wiregraph walks `request.user.tenant_memberships`. Point `TENANT_RESOLVER` at your own callable if your project stores tenancy differently (FK, subdomain, header).

## Retention purge

Delete events older than `DATA_RETENTION_DAYS`:

```bash
python manage.py wiregraph_purge [--dry-run]
```

Or via Celery Beat:

```python
import wiregraph.celery as wg_celery
CELERY_BEAT_SCHEDULE = {**wg_celery.schedule(hour=3, minute=0)}
```

## API

> Requires `pip install wiregraph[drf]`. Without the extra, `/api/v1/` routes are not registered.

Versioned under `/api/v1/`, JWT `Bearer` auth (obtain via `/api/v1/auth/token/`). OpenAPI at `/api/v1/schema/`, Swagger at `/api/v1/schema/docs/`.

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/token/` | Obtain access + refresh token |
| POST | `/api/v1/auth/token/refresh/` | Rotate refresh token |
| GET | `/api/v1/detection/events/` | List events (filter: `direction`, `data_asset`, `endpoint`, `timestamp__gte`, `timestamp__lte`) |
| GET | `/api/v1/detection/events/{id}/` | Retrieve event |
| GET | `/api/v1/detection/assets/` | PII categories seen in traffic |
| GET | `/api/v1/detection/stats/summary/` | Dashboard counts |

See [docs/settings.md](docs/settings.md) for all config keys.

## Requirements

Python ≥ 3.10 · Django ≥ 4.2 · Celery + Redis (async detection) · PostgreSQL recommended

## License

MIT
