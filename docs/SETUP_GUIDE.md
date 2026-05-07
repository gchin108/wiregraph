# WireGraph — Setup Guide

Integrate WireGraph PII detection into a Django project in 3 steps. The rest of this guide is optional — read only the sections you need.

**What you get after setup:**
- Automatic scanning of every inbound request body and outbound response body
- Hashed, tenant-scoped audit trail of every PII event
- Signals your own code can subscribe to for alerting
- An admin dashboard that visualizes data flow as a three-column graph

---

## Quick start

```bash
pip install wiregraph
```

```python
# settings.py
import wiregraph

INSTALLED_APPS = [..., *wiregraph.INSTALLED_APPS]
MIDDLEWARE     = wiregraph.setup(MIDDLEWARE)
WIREGRAPH      = {"ENABLED": True}
```

```bash
python manage.py migrate
python manage.py wiregraph_doctor   # verify configuration
```

That's it. Inbound/outbound request bodies are now scanned for PII. Visit `/admin/wiregraph/dashboard/` (as staff) to see the graph.

Prefer a scaffolder? `python manage.py wiregraph_init --settings-file <path>` appends the block for you.

---

## Table of Contents

- [Quick start](#quick-start) ↑
- [Requirements](#requirements)
- [Installing Presidio](#installing-presidio)
- [Settings reference](#settings-reference)
- [Advanced topics](#advanced-topics)
  - [Custom tenant resolution](#custom-tenant-resolution)
  - [Egress tracking](#egress-tracking-opt-in)
  - [Allowlists](#allowlists)
  - [Signal handlers](#signal-handlers)
  - [Admin dashboard](#admin-dashboard)
  - [Retention & cleanup](#retention--cleanup)
  - [Custom AdminSite](#custom-adminsite)
- [Troubleshooting](#troubleshooting)
- [Production hardening](#production-hardening)
- [Appendix: file reference](#appendix-file-reference)

---

## Requirements

- Python 3.10+
- Django 4.2, 5.0, 5.1, or 5.2
- Django REST Framework *(optional — only required for the JSON API and JWT auth; install via `pip install 'wiregraph[drf]'`. The core scanning pipeline and bundled admin dashboard work without it.)*
- Celery + a broker *(optional — only required for async Presidio scans and for scheduling the bundled purge task via Celery Beat; install via `pip install 'wiregraph[celery]'`. Synchronous regex scanning and the `wiregraph_purge` management command work without it.)*
- A Django-supported database (PostgreSQL, MySQL, SQLite, or Oracle)
- A tenant model. WireGraph is tenant-scoped by design — every event belongs to exactly one tenant. The default resolver walks `request.user.tenant_memberships`; see [Custom tenant resolution](#custom-tenant-resolution) if your model differs.

---

## Installing Presidio

Presidio is an optional extra. Both the Python packages *and* a spaCy language model are required — the model is distributed separately from PyPI and must be downloaded as a post-install step.

**Local / virtualenv:**

```bash
pip install 'wiregraph[presidio]'
python -m spacy download en_core_web_lg
```

**Dockerfile:**

```dockerfile
RUN pip install 'wiregraph[presidio]' \
    && python -m spacy download en_core_web_lg
```

Quote `'wiregraph[presidio]'` — unquoted brackets get interpreted by the shell. `wiregraph_doctor` will warn if `ENABLE_PRESIDIO` is on but the spaCy model isn't loadable.

---

## Settings reference

`WIREGRAPH["ENABLED"]` is the **only required key**. Every other key has a sensible default. See [settings.md](./settings.md) for the full table of 28 keys, types, and defaults.

The ones you're most likely to touch:

| Key | Default | Why you'd change it |
|---|---|---|
| `ENABLED` | `False` | Flip to `True` — this is the master switch. |
| `ENABLE_EGRESS_TRACKING` | `False` | Enable outbound `requests` interception. |
| `SAMPLING_RATE` | `1.0` | Lower for high-volume endpoints where full scanning is too expensive. |
| `EXCLUDED_PATHS` | `[]` | Skip health checks, metrics, static files. |
| `MAX_BODY_SIZE` | `1_048_576` | Tune to your p99 payload size. |
| `DATA_RETENTION_DAYS` | `90` | Match your compliance regime. |
| `TENANT_RESOLVER` | `"wiregraph.resolvers.default"` | Point at your own callable if your tenancy model differs. |

---

## Advanced topics

### Custom tenant resolution

By default WireGraph walks `request.user.tenant_memberships` and picks the oldest membership. If your project stores tenancy differently — active-tenant FK on the user, a subdomain, a gateway header — point `TENANT_RESOLVER` at a callable:

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

The callable receives the raw `HttpRequest` and must return a `Tenant` instance or `None`. Returning `None` causes the scan to be skipped silently — this is expected for anonymous traffic.

### Egress tracking (opt-in)

Outbound HTTP interception is off by default. Turn it on:

```python
WIREGRAPH = {"ENABLED": True, "ENABLE_EGRESS_TRACKING": True}
```

What it does:
- Monkey-patches `requests.Session.send` at app startup (`EgressConfig.ready()`).
- Every outbound `requests` call records an `ExternalService` touch.
- Request bodies are scanned; matches create `DataEvent` rows with `direction="egress"` and fire the `egress_pii_leak` signal.

**Scope:** `requests.*` and `Session.send` are caught. `httpx`, `aiohttp`, raw sockets, `urllib`, and gRPC are **not**.

**Depends on `PIIDetectionMiddleware`.** The interceptor reads the active tenant from a `ContextVar` that the middleware sets per request. `wiregraph.setup(MIDDLEWARE)` installs the middleware for you; if you wire middleware manually, make sure `PIIDetectionMiddleware` is present.

**Recursion safety** — internal traffic (your own alert webhooks) should not be re-intercepted:

```python
from wiregraph_apps.egress.interceptor import mark_internal_call
with mark_internal_call():
    requests.post("https://my-own-webhook.internal/alert", json={...})
```

Or set the `X-Wiregraph-Internal: 1` header.

**Disabling for tests** — set `DISABLE_EGRESS_PATCHING=True` to avoid conflicts with `responses` / `requests-mock` / `VCR.py`.

### Allowlists

Suppress known false positives per-tenant via the `AllowlistRule` table.

```http
POST /api/v1/detection/allowlist-rules/
{
  "asset_name": "email",
  "endpoint_prefix": "/api/v1/notifications/",
  "reason": "Notification system receives user emails by design"
}
```

- `asset_name` — PII type to suppress; `"*"` matches all.
- `endpoint_prefix` — URL prefix; `"*"` for all endpoints.
- `reason` — required for audit.

Cache invalidation is automatic when rules change via the API. If you mutate rules directly in the DB, call `invalidate_tenant_rules(tenant)` from `wiregraph_apps.detection.adapters.allowlist`.

### Signal handlers

Four signals are emitted. **Prefer `event_classified` for alert routing** — it carries the confidence-gated `effective_level` so receivers don't have to recompute it. The others are kept for backwards compatibility and narrower use cases.

| Signal | Fired when | Kwargs |
|---|---|---|
| `event_classified` | After classification on inbound *and* egress paths (recommended for alerts) | `data_event`, `external_service`, `effective_level`, `confidence`, `reason` |
| `pii_detected` | After a `DataEvent` is persisted on inbound or async paths (not egress) | `data_event`, `request` |
| `new_data_asset_discovered` | First time a given `DataAsset.name` is seen for a tenant | `data_asset`, `tenant` |
| `egress_pii_leak` | A `prohibited` egress `DataEvent` is created | `data_event`, `external_service` |

```python
from django.dispatch import receiver
from wiregraph_apps.detection.signals import event_classified

@receiver(event_classified)
def alert(sender, data_event, external_service, effective_level, confidence, reason, **kwargs):
    if effective_level == "prohibited":
        send_to_pagerduty(
            summary=f"PII leak: {data_event.data_asset.name} → {external_service.domain if external_service else 'inbound'}",
            severity="critical",
        )
```

Register in your app's `AppConfig.ready()` by importing the module.

Handlers run **synchronously** inside the request cycle. Delegate slow work (webhooks, email) to Celery.

**Bundled webhook.** If `ALERT_WEBHOOK_URL` is set, built-in handlers POST a summary there. Turn them off with `DISABLE_BUILTIN_ALERTS=True` when you wire your own.

### Admin dashboard

Auto-registered at `/admin/wiregraph/dashboard/`. Requires `is_staff=True`.

A three-column directed graph (D3.js, CDN-loaded):

```
Inbound Endpoints  →  PII Types  →  External Services
```

JSON API for BI export:

```bash
curl -s -b "sessionid=..." \
  "https://your-app.com/admin/wiregraph/dashboard/?format=json&start=2026-01-01&end=2026-01-31"
```

### Retention & cleanup

`DataEvent` rows accumulate until purged. Purge old rows with:

```bash
python manage.py wiregraph_purge [--dry-run] [--batch-size N] [--retention-days N]
```

Respects `DATA_RETENTION_DAYS`. Deletes in batches to bound transactions.

**Celery Beat** — requires `pip install 'wiregraph[celery]'`. Merge the bundled schedule fragment:

```python
import wiregraph.celery as wg_celery

CELERY_BEAT_SCHEDULE = {
    **wg_celery.schedule(hour=3, minute=0),
    # ... your other scheduled tasks ...
}
```

The task `wiregraph.celery.purge_expired_events` is registered automatically when `wiregraph_apps.reporting` loads, provided Celery is installed. Without the `[celery]` extra, `wg_celery.schedule(...)` raises `RuntimeError` — use the `wiregraph_purge` management command from cron/systemd instead.

### Custom AdminSite

If you run a custom `AdminSite`, point the dashboard at it:

```python
WIREGRAPH = {
    "ENABLED": True,
    "ADMIN_SITE": "myproject.admin.my_custom_site",
}
```

---

## Troubleshooting

Run `python manage.py wiregraph_doctor` first — it runs eight checks (enabled flag, tenant resolver, middleware order, egress patch state, `DataEvent` indexes, cache adapter, sink overrides, DRF API extra).

| Symptom | Cause | Fix |
|---|---|---|
| No events ever created | Anonymous endpoints, or auth middleware after `PIIDetectionMiddleware` | Use `wiregraph.setup(MIDDLEWARE)`; check that users authenticate |
| No events for a specific user | User has no tenant | Check your `TENANT_RESOLVER`; create a membership if using the default |
| Egress events missing | Using `httpx`, or `ENABLE_EGRESS_TRACKING=False` | Enable the setting; switch to `requests` |
| Tests hang or hit real HTTP | Interceptor conflicts with `responses`/VCR | Set `DISABLE_EGRESS_PATCHING=True` in test settings |
| Dashboard returns 403 | User is not staff | Grant `is_staff=True` |
| Large requests not scanned | Body > `MAX_BODY_SIZE` | Raise limit or accept gap |
| Infinite loop in alerts | Your webhook is re-intercepted | Wrap in `mark_internal_call()` |
| Allowlist change ignored | Per-tenant cache stale | Call `invalidate_tenant_rules(tenant)` |
| Presidio install fails in Docker (`permission denied` on `~/.local`) | Base image's user has no `HOME` | Set `ENV HOME=/home/<user>` and ensure the dir exists before `pip install` |

---

## Production hardening

- [ ] `ENABLED=True` and `wiregraph_doctor` exits `0`
- [ ] `ENABLE_EGRESS_TRACKING=True` (after staging validation)
- [ ] `DISABLE_EGRESS_PATCHING=False` (only `True` in tests)
- [ ] `REDACT_STRATEGY="hash"` (not `"mask"` unless legally required)
- [ ] `MAX_BODY_SIZE` tuned to your p99 payload size
- [ ] `EXCLUDED_PATHS` includes health checks, metrics, static files
- [ ] `DATA_RETENTION_DAYS` matches compliance policy
- [ ] `wiregraph_purge` scheduled daily via cron or Celery Beat
- [ ] Signal handlers that do I/O delegate to Celery
- [ ] `/admin/wiregraph/dashboard/` behind VPN or SSO
- [ ] Alert webhooks wrapped in `mark_internal_call()`
- [ ] Monitoring on: `DataEvent.bulk_create` failures, unusual drop in event volume, spikes in `egress_pii_leak`
- [ ] Load test — middleware adds ~5–20ms at `SAMPLING_RATE=1.0`

---

## Appendix: file reference

| Concern | File |
|---|---|
| Public API (`setup`, `INSTALLED_APPS`, `resolvers`) | `wiregraph/` |
| Inbound/outbound middleware | `wiregraph_apps/detection/middleware.py` |
| Egress interceptor | `wiregraph_apps/egress/interceptor.py` |
| Settings resolution | `wiregraph_apps/common/conf.py` |
| Tenant resolution | `wiregraph_apps/common/tenancy.py`, `wiregraph/resolvers.py` |
| Signals | `wiregraph_apps/detection/signals.py`, `wiregraph_apps/egress/signals.py` |
| Allowlist | `wiregraph_apps/detection/allowlist.py` |
| Admin dashboard | `wiregraph_apps/common/admin_views.py`, `wiregraph_apps/common/templates/admin/wiregraph/dashboard.html` |
| Management commands | `wiregraph_apps/common/management/commands/`, `wiregraph_apps/reporting/management/commands/` |
| Purge core | `wiregraph_apps/reporting/purge.py` |
| Celery task + schedule helper | `wiregraph/celery.py` |
