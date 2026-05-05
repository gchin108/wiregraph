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
- **Done when:** `grep -rn "rest_framework\|drf_spectacular" src/wiregraph_apps/ | grep -v /api/` returns nothing; full test suite passes with `[drf]` installed.

### Phase 3 — Conditional URL inclusion (0.5 day)
- `wiregraph/urls.py` (or wherever `/api/v1/` is wired): wrap the `include("wiregraph_apps.<app>.api.urls")` calls in a `try: import rest_framework` guard. When DRF is absent, the API routes simply aren't registered; admin routes remain.
- Add a startup log line at INFO when API routes are skipped, so consumers know why `/api/v1/` 404s.
- **Done when:** in a no-DRF venv, `manage.py check` passes, `manage.py runserver` boots, `/admin/wiregraph/dashboard/` renders, `/api/v1/detection/events/` returns 404.

### Phase 4 — `wiregraph_doctor` API health check (0.5 day)
Extend the existing doctor command (ring 2 phase 5) with API-surface awareness.
- Add `_check_api_extra`: detects whether DRF is importable; if so, asserts each `<app>/api/urls.py` resolves; if not, prints an info line ("API extra not installed — install wiregraph[drf] to enable /api/v1/").
- **Done when:** `wiregraph_doctor` reports API status accurately in both extras-installed and base-only environments.

### Phase 5 — Test matrix (1 day)
- Add a tox/CI job that installs the base package without `[drf]` and runs a smoke test subset (middleware, persistence, admin dashboard view, doctor command). This is the regression guard for "did someone reintroduce a hard DRF import?"
- Existing full suite continues to run with `[all]`.
- **Done when:** CI has two columns — `base` and `all` — both green.

### Phase 6 — Documentation & migration note (0.5 day)
- README: install matrix table, when to pick which extra, dashboard-vs-API distinction.
- CHANGELOG: ring 3 is consumer-visible if DRF was previously a hard dep — call it out as a minor breaking change for anyone whose installer didn't pin extras.
- `wiregraph_init` scaffolder: if it injects API URL patterns, gate that behind a `--with-api` flag.
- **Done when:** a new consumer can read the README and pick the right install line on first try.

## Tests
- New `tests/test_no_drf/` directory with conftest that monkeypatches `sys.modules` to hide `rest_framework`; covers middleware, persistence, admin dashboard view, doctor.
- Existing API tests stay put under `tests/test_api/` (or wherever they live), run only when DRF is installed.
- Assertion in `tests/test_imports.py`: `import wiregraph_apps.detection.middleware` must not transitively import `rest_framework`.

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
| 5. No-DRF test matrix | 1d | No |
| 6. Docs & migration note | 0.5d | No |
| **Total** | **~4 days** | |
