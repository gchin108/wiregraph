# Ring 1 Extraction Plan — Pure-Python Detection Core

## Goal
Extract a framework-agnostic detection core from `wiregraph_apps.detection` so a future FastAPI (or other) integration can reuse `scanner + classifier + sinks + allowlist` without importing Django. Phased so work can pause between phases without leaving the tree broken.

## Target structure
```
wiregraph/src/
  wiregraph_core/                 # NEW — pure Python, no Django
    __init__.py
    scanner/
      regex.py                    # from detection/regex_scanner.py
      presidio.py                 # from detection/presidio_scanner.py
    classifier.py                 # pure classify() only
    sinks.py                      # builtin catalog only
    allowlist.py                  # rule matching, no ORM
    escalation.py                 # counter logic, no ORM
    dedup.py                      # already pure
    types.py                      # dataclasses: Match, Asset, Sink, Outcome, Decision
    cache.py                      # CacheProtocol (get/set/incr)
    config.py                     # DetectionConfig dataclass
  wiregraph_apps/detection/       # remains — Django wrapper
    middleware.py                 # parses request → calls core → persists
    persistence.py                # ORM writes, signals
    classifier_django.py          # ORM-aware wrapper around core.classify
    sinks_django.py               # builtin + SinkCatalogOverride merge
    allowlist_django.py           # AllowlistRule.objects → core.AllowlistEngine
    cache_django.py               # CacheProtocol impl over django.core.cache
    tasks.py                      # Celery wrapper, unchanged
    signals.py, receivers.py      # unchanged
    models.py                     # unchanged
```

## Phases (each leaves tree green)

### Phase 0 — Define core types & contracts (0.5 day)
- Create `wiregraph_core/` package with `types.py`, `cache.py`, `config.py`.
- No behavior moves yet. Just dataclasses + Protocol definitions.
- **Done when:** `from wiregraph_core.types import Match, Outcome` works; tests still pass.

### Phase 1 — Move trivially-pure modules (1 day)
- Move `dedup.py`, `presidio_scanner.py` to `wiregraph_core/`.
- Update imports in `detection/middleware.py`, `detection/tasks.py`.
- **Done when:** `grep django wiregraph_core/dedup.py wiregraph_core/scanner/presidio.py` returns nothing; tests pass.

### Phase 2 — Extract config-injectable modules (3 days)
- `regex_scanner.py` → `wiregraph_core/scanner/regex.py` accepting `DetectionConfig` instead of reading `conf.py`.
- `escalation.py` counter logic → core; ORM writes stay in `detection/escalation_django.py`.
- `allowlist.py` rule matching → core (`AllowlistEngine.matches(rule_data, event)`); `AllowlistRule.objects.filter()` stays in `allowlist_django.py`.
- `sinks.py` builtin catalog → core; override merging stays in `sinks_django.py`.
- Replace `django.core.cache` usage with injected `CacheProtocol`.
- **Done when:** core modules import nothing from `django.*`; Django wrappers import core + ORM.

### Phase 3 — Split classifier (1 week)
This is the hardest piece. `classify_for_event()` mixes pure logic with `DataEvent.objects.filter` and shadow-counter writes.
- Extract pure `classify(asset, sink, policy, history) -> Decision` to `wiregraph_core/classifier.py`. `history` is a small dataclass passed in by caller.
- New `detection/classifier_django.py` does: query history from ORM → call pure `classify()` → write shadow counter via ORM.
- Update `middleware.py` and `tasks.py` to call the Django wrapper.
- **Done when:** `wiregraph_core/classifier.py` has no ORM/`F`/`dispatch` imports.

### Phase 4 — Gate DRF behind extras (1–2 days, *optional but recommended*)
- Move `serializers.py`, the API views (`views.py`), and `urls.py` under `wiregraph_apps/detection/api/` (separate subpackage).
- Add `[drf]` extra in `pyproject.toml` and conditionally register URLs only when DRF is installed.
- **Note:** This is independent of phases 0–3. Can be done first or last.

### Phase 5 — Dashboard-specific code (separate audit, not part of ring 1)
- Out of scope for this plan. Tracked separately: `selectors.py`, `EndpointNodeViewSet`, sparkline serializers. Revisit after ring 1 lands.

## Tests
- Existing `tests/` stays put. Each phase updates imports only.
- Add `tests/test_core/` mirroring `wiregraph_core/` with no Django setup — proves core is importable standalone.
- `tests/conftest.py` keeps `django.setup()` for the integration tests.

## Rollback safety
Every phase is independently revertable. Phase 0 adds files only. Phases 1–3 are mechanical moves with import updates; if a phase ships and the next stalls, the tree still works — wrappers just delegate to whatever's been extracted.

## Risk register
- **`conf.py` is read in many places** — auditing every settings access is the tedious part of phase 2. Estimate could grow if there are dynamic accesses we missed.
- **Celery tasks import detection modules** — `tasks.py` import paths need updating in phase 1; missing one is a runtime error, not import error. Run the integration tests, not just unit.
- **Public API:** `wiregraph.setup()` and `wiregraph.INSTALLED_APPS` don't change — consumers' `settings.py` is untouched.

## Effort summary
| Phase | Effort | Blocking next? |
|---|---|---|
| 0. Types & contracts | 0.5d | No |
| 1. Trivial moves | 1d | No |
| 2. Config-injectable | 3d | Yes (for phase 3) |
| 3. Classifier split | 5–7d | No |
| 4. DRF extra | 1–2d | No |
| **Total** | **~2–3 weeks** | |
