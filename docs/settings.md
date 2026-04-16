# WireGraph Settings Reference

All WireGraph configuration lives in a single `WIREGRAPH` dict in your Django settings.

**Only `ENABLED` is required.** Every other key has a sensible default.

```python
WIREGRAPH = {
    "ENABLED": True,
}
```

For IDE completion, the `WiregraphSettings` TypedDict is exported:

```python
from core_apps.common.conf import WiregraphSettings

WIREGRAPH: WiregraphSettings = {
    "ENABLED": True,
}
```

## All keys

| Key | Type | Default | Description |
|---|---|---|---|
| `ENABLED` | `bool` | `False` | Master switch. When `False`, middleware is inert and no events are recorded. |
| `ENABLE_PRESIDIO` | `bool` | `False` | Enable Microsoft Presidio as a secondary detection engine alongside regex. Requires `presidio-analyzer` + `presidio-anonymizer`. Higher CPU cost per request. |
| `ENABLE_EGRESS_TRACKING` | `bool` | `False` | Master switch for the outbound `requests` interceptor. See SETUP_GUIDE §8. |
| `DISABLE_EGRESS_PATCHING` | `bool` | `False` | Hard override that skips the monkey-patch even when `ENABLE_EGRESS_TRACKING=True`. Intended for test runners using `responses`/`VCR.py`. Leave `False` in production. |
| `DATA_RETENTION_DAYS` | `int` | `90` | Age at which `DataEvent` rows become eligible for purging via the `wiregraph_purge` command. Tune per compliance regime (GDPR often 30–90 days, HIPAA typically 6 years). |
| `REDACT_STRATEGY` | `str` | `"hash"` | How matched PII is recorded in `redacted_snippet`. One of `"hash"` (SHA-256 first 16 hex), `"mask"` (character-masked preview), or `"none"` (empty string). Recommendation: `"hash"` for almost all cases. |
| `ALERT_WEBHOOK_URL` | `str \| None` | `None` | URL that default signal handlers POST to on high-severity events. `None` disables the built-in webhook. |
| `ALLOWLISTED_FIELDS` | `list[str]` | `[]` | Global, across-tenant field-name allowlist. Matches inside fields named here are suppressed before persistence. Example: `["internal_user_id"]`. |
| `SAMPLING_RATE` | `float` | `1.0` | Fraction of requests to scan (`0.0`–`1.0`). At `0.1`, 10% of requests are scanned. Sampled-out requests produce zero events, so dashboards undercount by `1/SAMPLING_RATE`. |
| `MAX_BODY_SIZE` | `int` | `1_048_576` | Maximum body size to scan, in bytes. Bodies larger than this skip the scan (the request/response passes through unchanged). Protects against DoS and pathological scan times. |
| `EXCLUDED_PATHS` | `list[str]` | `[]` | URL prefixes to skip entirely. Prefix match: `"/api/v1/webhooks/"` skips `/api/v1/webhooks/stripe/...` as well. Typical entries: `["/healthz", "/readyz", "/metrics", "/static/", "/media/"]`. |
| `TENANT_RESOLVER` | `str` | `"wiregraph.resolvers.default"` | Dotted path to a `(HttpRequest) -> Tenant \| None` callable. Override when your project resolves tenancy differently (active-tenant FK, subdomain, gateway header, etc.). |
| `TENANT_MODEL` | `str` | `"tenants.Tenant"` | `"app_label.Model"` reference for the tenant model; used when a custom resolver needs `apps.get_model()`. |
| `DISABLE_BUILTIN_ALERTS` | `bool` | `False` | When `True`, the bundled webhook receivers (`alert_on_pii_detected`, `alert_on_new_asset`, `alert_on_egress_leak`) short-circuit. Use when you wire your own Slack/PagerDuty handlers and don't want the built-ins firing. |
| `ADMIN_SITE` | `str` | `"django.contrib.admin.site"` | Dotted path to the `AdminSite` instance that should host the WireGraph dashboard URL. Override when you run a custom AdminSite. |

## Related reading

- [SETUP_GUIDE.md](./SETUP_GUIDE.md) — end-to-end integration walkthrough
- [SETUP_GUIDE §9](./SETUP_GUIDE.md#9-the-wiregraph-settings-dict--every-option-explained) — longer prose explanations for each key
