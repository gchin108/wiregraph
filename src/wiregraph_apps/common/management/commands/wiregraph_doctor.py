"""Self-check command that surfaces common WireGraph misconfigurations.

Run ``python manage.py wiregraph_doctor``. Prints a checklist; exits ``0`` if
everything looks sane and ``1`` if any check fails. Intended for use in
staging smoke tests and local troubleshooting.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

OK = "[OK]"
WARN = "[WARN]"
FAIL = "[FAIL]"


class Command(BaseCommand):
    help = "Inspect WireGraph configuration and report issues."

    def handle(self, *args, **options):
        checks = [
            self._check_enabled,
            self._check_tenant_resolver,
            self._check_middleware_order,
            self._check_egress_patch_state,
            self._check_dataevent_indexes,
            self._check_cache_adapter,
            self._check_sink_overrides,
        ]
        has_failure = False
        for check in checks:
            status, message = check()
            self.stdout.write(f"{status} {message}")
            if status == FAIL:
                has_failure = True

        if has_failure:
            self.stderr.write("\nwiregraph_doctor: one or more checks failed.")
            raise SystemExit(1)

    def _check_enabled(self):
        from wiregraph_apps.common.conf import is_enabled

        if is_enabled():
            return OK, "ENABLED=True"
        return WARN, "ENABLED=False — middleware is inert"

    def _check_tenant_resolver(self):
        try:
            from wiregraph.resolvers import load_configured

            resolver = load_configured()
            return OK, f"tenant resolver: {resolver.__module__}.{resolver.__name__}"
        except Exception as exc:
            return FAIL, f"tenant resolver failed to load: {exc}"

    def _check_middleware_order(self):
        from django.conf import settings

        from wiregraph.setup import DJANGO_AUTH, JWT_AUTH, PII_DETECTION

        middleware = list(getattr(settings, "MIDDLEWARE", []))
        if PII_DETECTION not in middleware:
            return FAIL, f"{PII_DETECTION} missing from MIDDLEWARE"

        pii_idx = middleware.index(PII_DETECTION)
        if JWT_AUTH in middleware and middleware.index(JWT_AUTH) >= pii_idx:
            return FAIL, "JWTAuthMiddleware must precede PIIDetectionMiddleware"
        if DJANGO_AUTH in middleware and middleware.index(DJANGO_AUTH) >= pii_idx:
            return FAIL, "AuthenticationMiddleware must precede PIIDetectionMiddleware"
        return OK, "MIDDLEWARE order looks correct"

    def _check_egress_patch_state(self):
        from wiregraph_apps.common.conf import get_config
        from wiregraph_apps.egress.interceptor import _patch_state

        enabled = get_config("ENABLE_EGRESS_TRACKING")
        disabled = get_config("DISABLE_EGRESS_PATCHING")
        installed = _patch_state.get("installed", False)

        if not enabled:
            return OK, "egress tracking disabled (ENABLE_EGRESS_TRACKING=False)"
        if disabled:
            return WARN, "ENABLE_EGRESS_TRACKING=True but DISABLE_EGRESS_PATCHING=True"
        if not installed:
            return FAIL, "egress tracking enabled but patch not installed"
        return OK, "egress patch installed"

    def _check_dataevent_indexes(self):
        from django.db import connection

        from wiregraph_apps.detection.models import DataEvent

        table = DataEvent._meta.db_table
        try:
            with connection.cursor() as cursor:
                existing = connection.introspection.get_constraints(cursor, table)
        except Exception as exc:
            return WARN, f"could not inspect DB indexes: {exc}"

        index_count = sum(1 for c in existing.values() if c.get("index"))
        if index_count == 0:
            return FAIL, f"no indexes found on {table} — run migrate"
        return OK, f"{table} has {index_count} index(es)"

    def _check_cache_adapter(self):
        from wiregraph_apps.detection.adapters.cache import get_cache
        from wiregraph_core.cache import CacheProtocol

        try:
            backend = get_cache()
        except Exception as exc:
            return FAIL, f"cache adapter failed to load: {exc}"
        if not isinstance(backend, CacheProtocol):
            return FAIL, (
                f"cache backend {type(backend).__name__} does not satisfy "
                f"CacheProtocol (needs get/set/add/incr/delete)"
            )
        return OK, f"cache adapter: {type(backend).__module__}.{type(backend).__name__}"

    def _check_sink_overrides(self):
        from wiregraph_apps.common.conf import get_sink_overrides
        from wiregraph_apps.detection.adapters.sinks import resolve_sink

        overrides = get_sink_overrides()
        if not overrides:
            return OK, "no SINK_OVERRIDES configured"

        bad: list[str] = []
        for suffix in overrides:
            try:
                info = resolve_sink(suffix)
            except Exception as exc:
                bad.append(f"{suffix} (raised {exc.__class__.__name__})")
                continue
            if info.category == "unknown" or info.trust_tier == "unknown":
                bad.append(f"{suffix} (resolved to unknown category/tier)")

        if bad:
            return FAIL, "SINK_OVERRIDES failed to resolve: " + ", ".join(bad)
        return OK, f"SINK_OVERRIDES resolve cleanly ({len(overrides)} entry(ies))"
