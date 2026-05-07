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
from wiregraph_apps.common.conf import WiregraphSettings

WIREGRAPH: WiregraphSettings = {
    "ENABLED": True,
}
```

## All keys

| Key | Type | Default | Description |
|---|---|---|---|
| `ENABLED` | `bool` | `False` | Master switch. When `False`, middleware is inert and no events are recorded. |
| `ENABLE_PRESIDIO` | `bool` | `False` | Enable Microsoft Presidio as a secondary (async) detection engine. Middleware enqueues each scannable payload to Celery (`wiregraph.detection.scan_payload_async`); results persist as `DataEvent(detection_method="presidio")`. Requires `pip install wiregraph[presidio]` plus `python -m spacy download en_core_web_lg` and a running Celery worker. |
| `CUSTOM_PATTERNS` | `list[dict]` | `[]` | User-registered regex detectors merged into the fast regex scanner. Each entry: `{"name": str, "regex": str, "confidence": float = 0.75, "flags": str = ""}`. Flags are a string of `imsxa` characters mapped to `re.IGNORECASE`/`MULTILINE`/`DOTALL`/`VERBOSE`/`ASCII`. Invalid specs raise `ImproperlyConfigured` at startup. Example: `[{"name": "emp_id", "regex": r"\bEMP-\d{6}\b", "confidence": 0.9}]`. |
| `ENABLE_EGRESS_TRACKING` | `bool` | `False` | Master switch for the outbound `requests` interceptor. See [SETUP_GUIDE — Egress tracking](./SETUP_GUIDE.md#egress-tracking-opt-in). |
| `DISABLE_EGRESS_PATCHING` | `bool` | `False` | Hard override that skips the monkey-patch even when `ENABLE_EGRESS_TRACKING=True`. Intended for test runners using `responses`/`VCR.py`. Leave `False` in production. |
| `DATA_RETENTION_DAYS` | `int` | `90` | Age at which `DataEvent` rows become eligible for purging via the `wiregraph_purge` command. Tune per compliance regime (GDPR often 30–90 days, HIPAA typically 6 years). |
| `REDACT_STRATEGY` | `str` | `"hash"` | How matched PII is recorded in `redacted_snippet`. One of `"hash"` (SHA-256 first 16 hex), `"mask"` (character-masked preview), or `"none"` (empty string). Recommendation: `"hash"` for almost all cases. |
| `ALERT_WEBHOOK_URL` | `str \| None` | `None` | URL that default signal handlers POST to on high-severity events. `None` disables the built-in webhook. |
| `ALLOWLISTED_FIELDS` | `list[str]` | `[]` | Global, across-tenant field-name allowlist. Matches inside fields named here are suppressed before persistence. Example: `["internal_user_id"]`. |
| `SAMPLING_RATE` | `float` | `1.0` | Fraction of requests to scan (`0.0`–`1.0`). At `0.1`, 10% of requests are scanned. Sampled-out requests produce zero events, so dashboards undercount by `1/SAMPLING_RATE`. |
| `MAX_BODY_SIZE` | `int` | `1_048_576` | Maximum body size to scan, in bytes. Bodies larger than this skip the scan (the request/response passes through unchanged). Protects against DoS and pathological scan times. |
| `EXCLUDED_PATHS` | `list[str]` | `[]` | URL prefixes to skip entirely. Prefix match: `"/api/v1/webhooks/"` skips `/api/v1/webhooks/stripe/...` as well. Typical entries: `["/healthz", "/readyz", "/metrics", "/static/", "/media/"]`. |
| `AUTO_EXCLUDE_ADMIN` | `bool` | `True` | Automatically skip scanning under the resolved Django admin URL prefix. Prevents a feedback loop where the DataEvent admin list re-detects the PII it displays. Set to `False` to opt out. |
| `AUTO_EXCLUDE_API` | `bool` | `True` | Automatically skip scanning under the mounted `wiregraph.api_urls` prefix (resolved from the `wiregraph-api-root` URL name). Prevents the JSON API's own redacted-PII responses from being re-scanned on every dashboard poll. Set to `False` to opt out. |
| `TENANT_RESOLVER` | `str` | `"wiregraph.resolvers.default"` | Dotted path to a `(HttpRequest) -> Tenant \| None` callable. Override when your project resolves tenancy differently (active-tenant FK, subdomain, gateway header, etc.). |
| `TENANT_MODEL` | `str` | `"wiregraph_tenants.Tenant"` | `"app_label.Model"` reference for the tenant model; used when a custom resolver needs `apps.get_model()`. |
| `DISABLE_BUILTIN_ALERTS` | `bool` | `False` | When `True`, the bundled webhook receivers (`alert_on_pii_detected`, `alert_on_new_asset`, `alert_on_egress_leak`) short-circuit. Use when you wire your own Slack/PagerDuty handlers and don't want the built-ins firing. |
| `PAGER_WEBHOOK_URL` | `str \| None` | `None` | Separate pager-grade webhook for `prohibited` events. Falls back to `ALERT_WEBHOOK_URL` when unset. Set this when you want `prohibited` to page (PagerDuty/Opsgenie) and lower-severity events to land in Slack via `ALERT_WEBHOOK_URL`. |
| `DEDUP_WINDOW_PROHIBITED_SECONDS` | `int` | `300` | Suppress duplicate `prohibited` alerts for the same (tenant, asset, sink, level) tuple within this window. Default 5 minutes. |
| `DEDUP_WINDOW_SUSPICIOUS_SECONDS` | `int` | `3600` | Same dedup idea for `suspicious`. Default 1 hour — wider since these are noisier. |
| `ESCALATION_SUSPICIOUS_COUNT` | `int` | `10` | When this many `suspicious` events for the same (tenant, asset, sink) fire within `ESCALATION_WINDOW_SECONDS`, subsequent ones escalate to `prohibited`. |
| `ESCALATION_WINDOW_SECONDS` | `int` | `86400` | Rolling window (default 24h) for the suspicious→prohibited escalation counter. |
| `ADMIN_SITE` | `str` | `"django.contrib.admin.site"` | Dotted path to the `AdminSite` instance that should host the WireGraph dashboard URL. Override when you run a custom AdminSite. |
| `LLM_POLICY` | `str` | `"strict"` | Classifier policy for LLM sinks. `"strict"`: medium+ PII → LLM is `prohibited`. `"relaxed"`: only high/critical. See classification proposal §3. |
| `SINK_OVERRIDES` | `dict` | `{}` | Merged over the built-in sink catalog (`sinks.py`) at startup. Use to add or reclassify destinations. Shape: `{"api.example.com": {"category": "llm", "trust_tier": "known", "accepts_assets": []}}`. |
| `CONFIDENCE_LOW` | `float` | `0.5` | Below this detector confidence, the shadow/effective alert level downgrades (`suspicious`→`acceptable`, `prohibited`→`suspicious`). Classification itself is unchanged. |
| `CONFIDENCE_HIGH` | `float` | `0.9` | Reserved for escalation policies. Not yet load-bearing. |
| `SHADOW_MODE` | `bool` | `False` | Phase 2 of the classification rollout. When `True`, every classified event gets `shadow_alert_level` computed and logged (`wiregraph.shadow`) and a `ShadowDecisionCounter` row is incremented. Alerting is unchanged — this is pure telemetry. Browse via the admin or `GET /api/v1/reporting/shadow/?days=7`. |

## Related reading

- [SETUP_GUIDE.md](./SETUP_GUIDE.md) — end-to-end integration walkthrough
