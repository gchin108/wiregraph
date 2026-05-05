# Ring 2 Integration Plan — Django Adapter Layer

## Goal
With the pure-python core (`wiregraph_core`) extracted in ring 1, ring 2 consolidates the Django side into a deliberate adapter layer that wraps the core. Today the Django pieces live in `wiregraph_apps.detection` (middleware, ORM, signals, admin, commands) plus the `*_django.py` wrappers ring 1 introduced. Ring 2 makes that boundary explicit, cleans up the seams, and ensures Django code only ever calls *into* the core — never the other way around. Phased so each step leaves the tree green.

**Out of scope:** DRF serializers, viewsets, routers, and the `[drf]` extra — those belong to ring 3, which imports from ring 2's adapter + persistence layer.

## Current state (2026-05-02)
The detection app already contains some of the target layout from ring 1:
- `persistence.py` and `allowlist.py` exist without the `_django` suffix.
- `cache_django.py` and `classifier_django.py` still carry the suffix — these are the remaining renames.
- `sinks.py` and `escalation.py` live in `wiregraph_core/` (ring 1); their Django wrappers were inlined elsewhere rather than given dedicated `*_django.py` files. Phase 0 will surface them as explicit adapter modules.
- `pipeline.py` does not exist yet.

## Target structure
```
wiregraph/src/wiregraph_apps/
  detection/
    adapters/                    # NEW — thin layer over wiregraph_core
      __init__.py
      classifier.py              # rename from classifier_django.py
      cache.py                   # rename from cache_django.py
      sinks.py                   # extract Django override-merge wrapper
      allowlist.py               # extract from existing allowlist.py (rule-loading wrapper)
      escalation.py              # extract Django ORM-write wrapper
    middleware.py                # HTTP parsing only → pipeline → persistence
    persistence.py               # already exists — consolidate remaining writes here
    pipeline.py                  # orchestration entry point (NEW, phase 2)
    signals.py, receivers.py     # formalized signal contract
    tasks.py                     # Celery wrapper
    models.py                    # ORM models
    admin.py                     # admin views
    selectors.py                 # read-side queries (unchanged in ring 2)
    serializers.py, views.py, urls.py   # ring 3 territory — untouched here
    management/commands/         # wiregraph_doctor, wiregraph_init
  egress/
    interceptor.py               # outbound HTTP → pipeline → persistence
  common/, tenants/, reporting/  # unchanged unless touched by a phase
```

## Phases (each leaves tree green)

### Phase 0 — Carve the adapter package (0.5 day)
- Create `wiregraph_apps/detection/adapters/`.
- Move and rename: `cache_django.py → adapters/cache.py`, `classifier_django.py → adapters/classifier.py`.
- Extract Django wrappers for `sinks` (override merge over `wiregraph_core.sinks`), `allowlist` (the ORM-loading half of today's `allowlist.py`), and `escalation` (ORM-write half of today's `escalation.py`) into `adapters/`. The pure pieces stay in `wiregraph_core`.
- Update imports across `middleware.py`, `tasks.py`, `egress/interceptor.py`, `admin.py`.
- **Done when:** `grep -r "_django" wiregraph_apps/` returns nothing; no module under `wiregraph_apps/detection/` (outside `adapters/`, `models.py`, `persistence.py`, `tasks.py`) imports both `wiregraph_core` and `models`; tests pass.

### Phase 1 — Consolidate ORM writes into `persistence.py` (2 days)
`persistence.py` already exists but ORM writes still live in `middleware.py`, `classifier_django.py`, `escalation.py`, and `tasks.py`. Pull the remaining writes behind it.
- Extend `persistence.py` to cover whatever isn't there yet: `record_event(decision, request_meta)`, `update_shadow_counter(...)`, `bulk_dedupe_persist(...)`.
- Middleware/tasks/egress/adapters call `persistence.*`; no `.objects.create` / `.objects.update` outside this module.
- **Done when:** `grep -rn "DataEvent.objects" wiregraph_apps/detection/ | grep -v persistence.py | grep -v selectors.py` is empty (selectors.py is read-only and stays).

### Phase 2 — Slim the middleware (2 days)
`detection/middleware.py` does request parsing, scanning orchestration, classification, persistence, and signal dispatch. Cut it back to HTTP-layer concerns.
- Extract orchestration to `detection/pipeline.py`: `run_pipeline(request_meta, body) -> list[Decision]`.
- Middleware: parse request → call `pipeline.run_pipeline` → call `persistence.record_event` for each decision → fire signals.
- **Done when:** `middleware.py` imports neither `wiregraph_core.*` nor `models.*` directly.

### Phase 3 — Formalize the signal contract (1 day)
Today `signals.py` and `receivers.py` are loosely coupled. Document the public signal surface so consumers can hook safely.
- Define typed signal payloads (dataclasses) in `detection/signals.py`.
- Add docstrings on each signal: who fires, who receives, what the payload guarantees.
- Audit `receivers.py` for any logic that should live in `persistence.py` instead.
- **Done when:** every `Signal()` in `signals.py` has a payload dataclass + docstring.

### Phase 4 — Egress interceptor parity (2 days)
`egress/interceptor.py` predates ring 1 and still calls scanner/classifier directly.
- Route it through `pipeline.run_pipeline` and `persistence.record_event` so request and egress paths share one code path.
- **Done when:** egress and detection middleware share the same orchestration entry point.

### Phase 5 — Admin & management commands audit (1 day) ✅
- `admin.py`: audited — no admin action re-implements adapter/persistence logic. The only side-effect on save/delete is `adapters.allowlist.invalidate_tenant_rules`, which is the correct entry point.
- `wiregraph_doctor`: added `_check_cache_adapter` (asserts `get_cache()` satisfies `CacheProtocol`) and `_check_sink_overrides` (resolves every configured suffix through `adapters.sinks.resolve_sink` and flags any that fall through to `unknown`).
- `wiregraph_init`: N/A — it's a settings-file scaffolder (appends `INSTALLED_APPS`/`MIDDLEWARE`/`WIREGRAPH` block); it does no catalog seeding or model inserts. Catalog seeding lives in the demo's `seed_demo` command, which already iterates `adapters.sinks.BUILTIN_CATALOG`.
- **Done when:** `wiregraph_doctor` reports adapter health; admin actions only call `persistence.*`. ✅

### Phase 6 — Models cleanup (1–2 days, *optional*)
Audit `detection/models.py` for fields that exist solely to bridge old direct-ORM call sites; remove or document any that ring 1 + the adapter layer have made redundant. Migration-cost gated; skip if churn outweighs benefit.

## Tests
- Existing integration tests stay put — they exercise the full Django stack and remain the ground truth.
- Add `tests/test_adapters/` covering each adapter in isolation with a fake `CacheProtocol` and minimal ORM fixtures.
- Add `tests/test_persistence.py` asserting `persistence.*` is the only writer for `DataEvent`.

## Rollback safety
Phases 0–5 are mechanical or additive. Each phase compiles and tests green independently. Phase 1 (persistence consolidation) is the riskiest — write paths are subtle — so land it behind a soak window before phase 2 builds on it.

## Risk register
- **Signal receiver ordering** — phase 3 can change which receiver runs first if you collapse logic into persistence. Add ordering tests before refactoring receivers.
- **Egress interceptor duplicates pipeline state** — phase 4 may reveal that egress needs a slightly different `request_meta` shape; expect a small `pipeline.run_pipeline` signature tweak.
- **Ring 1 phase 4 deferral** — gating DRF behind an extra was listed as optional in ring 1; it's now ring 3's responsibility. Ring 2 must not introduce new hard imports of `rest_framework` outside files that already import it.
- **Public API:** `wiregraph.setup()`, `wiregraph.INSTALLED_APPS`, middleware class names, and signal names don't change — consumers untouched.

## Effort summary
| Phase | Effort | Blocking next? |
|---|---|---|
| 0. Carve adapters | 0.5d | Yes (renames cascade) |
| 1. Persistence consolidation | 2d | Yes (for phase 2) |
| 2. Slim middleware | 2d | No |
| 3. Signal contract | 1d | No |
| 4. Egress parity | 2d | No |
| 5. Admin/commands audit | 1d | No |
| 6. Models cleanup | 1–2d | No |
| **Total** | **~1.5–2 weeks** | |
