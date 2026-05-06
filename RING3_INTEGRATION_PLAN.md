# Ring 3 Integration Plan — DRF Extraction & Dashboard-API Isolation

## Goal
With the Django adapter layer landed in ring 2, ring 3 isolates the DRF API surface — viewsets, serializers, routers, dashboard-shaped selectors — behind an optional `[drf]` extra. The core library + bundled admin dashboard at `/admin/wiregraph/dashboard/` remain installable with zero DRF dependency. Consumers who want the JSON API (notably the proprietary `wiregraph-dashboard` React app) opt in via `pip install wiregraph[drf]`.

This resolves the original concern that drove rings 1–2: dashboard-shaped logic should not be a hard dependency of the pip package.

**Out of scope:** the bundled admin dashboard (`common/admin_views.py`, `admin/wiregraph/dashboard/`) — that is intentional product surface and stays a default. Anything in `wiregraph_core` or `detection/adapters/` — already settled in rings 1–2.

## Current state (2026-05-04)
- DRF code lives in `detection/{views,serializers,urls}.py`, plus matching files in `egress/`, `reporting/`, `tenants/`. All import `rest_framework` at module load.
- `detection/selectors.py` exists to shape data for the React dashboard's endpoint-node card (sparkline, per-asset counts, worst-outcome). Its only non-trivial consumer is `detection/views.py`. Two helpers (`is_new_flow`, `is_new_flow_for_event`) are also imported by `adapters/classifier.py` — these are not dashboard-shaped.
- `pyproject.toml` likely already has a `[drf]` extra placeholder from ring 1 phase 4 (verify in phase 0); `rest_framework` may still be in the base install_requires.
- `common/admin_views.py` is self-contained — builds its own graph from `DataEvent`, does not import selectors or DRF.

## Target structure
```
wiregraph/src/wiregraph_apps/
  detection/
    api/                         # NEW — gated behind [drf] extra
      __init__.py                # imports guarded; raises clear error if DRF missing
      serializers.py             # moved from detection/serializers.py
      views.py                   # moved from detection/views.py
      urls.py                    # moved from detection/urls.py
      selectors.py               # moved from detection/selectors.py (dashboard-shaped reads)
    flow_state.py                # NEW — is_new_flow / is_new_flow_for_event (non-API)
    adapters/, middleware.py, persistence.py, pipeline.py, ...   # unchanged from ring 2
  egress/api/                    # same pattern: serializers/views/urls moved under api/
  reporting/api/                 # same
  tenants/api/                   # same
  common/
    admin_views.py               # unchanged — bundled OSS dashboard stays
    apps.py                      # unchanged — admin route still registers
wiregraph/src/wiregraph/
  urls.py                        # conditionally include api/urls only when DRF importable
```

## Phases (each leaves tree green)

### Phase 0 — Inventory & extras wiring (0.5 day)
- Audit `pyproject.toml`: confirm `[drf]` extra exists; if `djangorestframework` / `drf-spectacular` are still in base `dependencies`, move them to the extra.
- Add a `wiregraph._drf` helper module: `def require_drf(): try: import rest_framework except ImportError: raise ImproperlyConfigured("...pip install wiregraph[drf]...")`.
- Document the install matrix in README: base install vs `[drf]` vs `[all]`.
- **Done when:** `pip install wiregraph` (no extras) succeeds in a venv with no DRF on path; `python -c "import wiregraph; wiregraph.setup([])"` works; admin dashboard renders against a seeded DB.

### Phase 1 — Split `selectors.py` (0.5 day)
Separate the two concerns hiding in `detection/selectors.py`.
- Create `detection/flow_state.py` containing `is_new_flow`, `is_new_flow_for_event`, and any shared dataclasses they need. No DRF, no dashboard-shaped aggregation.
- Leave the rest of `selectors.py` (endpoint-node aggregation, sparkline buckets, asset counts) in place for now — it moves in phase 2.
- Update `adapters/classifier.py` to import from `flow_state`.
- **Done when:** `grep -rn "from wiregraph_apps.detection.selectors" src/wiregraph_apps/ | grep -v /api/ | grep -v views.py` is empty (only the soon-to-move DRF view imports selectors).

### Phase 2 — Move DRF modules into `api/` packages (1 day)
Mechanical relocation, one app at a time.
- For each of `detection`, `egress`, `reporting`, `tenants`: create `<app>/api/__init__.py`; move `serializers.py`, `views.py`, `urls.py` into it; for `detection`, also move the remaining `selectors.py` here.
- Update internal imports (`from .views` → `from .api.views`, etc.).
- Each `<app>/api/__init__.py` calls `wiregraph._drf.require_drf()` at import time so a missing extra produces a clear error, not a cryptic `ModuleNotFoundError`.
- **Done when:** `grep -rnE "^(from|import) (rest_framework|drf_spectacular)" src/wiregraph_apps/ | grep -v /api/` returns nothing — module-level imports only; lazy imports inside method bodies (e.g. `common/middleware.py`'s `JWTAuthMiddleware`) are intentional and keep module load DRF-free. Full test suite passes with `[drf]` installed.

### Phase 3 — Conditional URL inclusion + API auto-exclude (0.5 day)
- Ship a single library-owned `wiregraph.api_urls` urlconf that conditionally includes each `<app>.api.urls` based on `wiregraph._drf.drf_available()`. When DRF is absent, `urlpatterns` is empty; admin routes remain. Consumers mount it once: `path("api/v1/", include("wiregraph.api_urls"))`. Replaces the per-app includes currently in `config/urls.py` and `django-demo/demo/urls.py`.
- Within `api_urls`, anchor a sentinel pattern named `wiregraph-api-root` (e.g. an empty path returning a 200 "API root" stub) so the mount prefix is reverse-discoverable from anywhere in the project.
- Add an INFO log line when API routes are skipped, so consumers know why `/api/v1/` 404s.
- Add `AUTO_EXCLUDE_API` (default `True`) to the `WIREGRAPH` config and a `_resolve_api_prefix()` helper in `common/conf.py` that returns `reverse("wiregraph-api-root")` or `None` on `NoReverseMatch`. `get_excluded_paths()` appends it, mirroring `AUTO_EXCLUDE_ADMIN`. **Why this matters:** without it, the detection middleware re-scans the JSON API's own responses — `DataEventSerializer` emits redacted PII snippets that the regex/presidio scanner re-flags, generating fresh `DataEvent` rows on every dashboard poll and (under SQLite) deadlocking writers with `OperationalError: database is locked`.
- **Side effect to flag in the migration note (see phase 6):** because the PII middleware no longer runs on `/api/v1/`, `set_current_tenant` is not called for those requests, and `get_current_tenant()` returns `None` inside any view served under that prefix. Library DRF views are unaffected (`TenantScopedMixin` uses `resolve_tenant(request)` directly), but consumer-defined views must do the same.
- **Done when:** in a no-DRF venv, `manage.py check` passes, `runserver` boots, `/admin/wiregraph/dashboard/` renders, `/api/v1/detection/events/` returns 404. With `[drf]` installed, polling `/api/v1/detection/endpoint-nodes/` repeatedly does not increase the `DataEvent` row count (auto-exclude verified end-to-end).

### Phase 4 — `wiregraph_doctor` API health check (0.5 day)
Extend the existing doctor command (ring 2 phase 5) with API-surface awareness.
- Add `_check_api_extra`: detects whether DRF is importable; if so, asserts each `<app>/api/urls.py` resolves; if not, prints an info line ("API extra not installed — install wiregraph[drf] to enable /api/v1/").
- **Done when:** `wiregraph_doctor` reports API status accurately in both extras-installed and base-only environments.

### Phase 5 — Regression guard (0.5 day)
Two complementary checks; phase 5 owns both.
- **In-process** (runs inside the existing suite, no second tox column):
  - `tests/test_no_drf/` with a conftest that hides `rest_framework` via `sys.modules`. Covers middleware, persistence, admin dashboard view, doctor command.
  - `tests/test_imports.py` assertion: `import wiregraph_apps.detection.middleware` must not transitively import `rest_framework`.
- **Packaging guard** (one minimal CI step in a clean venv) — catches what `sys.modules` patching can't see (a runtime dep accidentally left in base `dependencies`, namespace-package quirks, conditional imports gated on installed metadata):
  - `pip install .` with no extras.
  - `python manage.py check` against the test project.
  - `python -c "import wiregraph_apps.detection.middleware; import wiregraph_apps.egress.interceptor"` — the eagerly-loaded hot-path modules, asserted against the real installed environment.
- **Done when:** existing CI is green and the packaging guard step passes without DRF on the path.

### Phase 6 — Documentation & migration note (0.5 day)
- README: install matrix table, when to pick which extra, dashboard-vs-API distinction.
- CHANGELOG: ring 3 is consumer-visible if DRF was previously a hard dep — call it out as a minor breaking change for anyone whose installer didn't pin extras.
- CHANGELOG / migration note — `get_current_tenant()` is no longer set on `/api/v1/` paths. `AUTO_EXCLUDE_API` (phase 3) skips the PII middleware for the API mount prefix, which means `set_current_tenant` is not called and `wiregraph_apps.common.tenancy.get_current_tenant()` returns `None` inside any view served under that prefix. Library DRF views are unaffected — they resolve via `TenantScopedMixin.get_tenant()` → `resolve_tenant(request)`, which works off `request.user` (set by `JWTAuthMiddleware` on every request, not gated by exclusion). Consumer-defined views mounted under `/api/v1/` that read the tenant ContextVar must switch to `resolve_tenant(request)`. Caught in the field by `django-demo/demo/views.py::egress_services`, which silently returned `[]` and broke the React dashboard's node graph.
- `wiregraph_init` scaffolder: if it injects API URL patterns, gate that behind a `--with-api` flag.
- **Done when:** a new consumer can read the README and pick the right install line on first try.

## Rollback safety
Phases 0–1 are additive. Phases 2–3 are the consumer-visible cut — land them together behind a single release. Phase 4–6 are additive polish. If the no-DRF install proves to break something we missed, reverting phase 3's URL guard restores prior behavior without code surgery.

## Risk register
- **Hidden DRF imports** — a serializer might be imported transitively by `admin.py` or a signal receiver. Phase 5's no-DRF CI job is the safety net; expect to find one or two on first run.
- **`drf-spectacular` schema generation** — if the schema endpoint is wired at the project URL conf level, gating it must not break `manage.py spectacular` for consumers who *do* have the extra.
- **Dashboard-app coupling** — `wiregraph-dashboard` (React) pins specific JSON shapes from `detection/api/serializers.py`. Moving the file is fine; changing field names is not. Don't refactor serializer shape during the move.
- **`wiregraph_init` scaffolder** — if it currently writes API URL patterns into the consumer's `urls.py` unconditionally, that becomes wrong post-ring-3. Phase 6 handles this.
- **Public API:** `wiregraph.setup()`, `wiregraph.INSTALLED_APPS`, middleware class names, signal names, admin dashboard URL — all unchanged.

## Effort summary
| Phase | Effort | Blocking next? |
|---|---|---|
| 0. Inventory & extras wiring | 0.5d | Yes |
| 1. Split selectors | 0.5d | Yes (for phase 2) |
| 2. Move DRF into api/ packages | 1d | Yes (for phase 3) |
| 3. Conditional URL inclusion | 0.5d | No |
| 4. Doctor API check | 0.5d | No |
| 5. Regression guard | 0.5d | No |
| 6. Docs & migration note | 0.5d | No |
| **Total** | **~3.5 days** | |
