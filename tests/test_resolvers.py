from unittest.mock import MagicMock

from django.test import RequestFactory, override_settings

from wiregraph import resolvers


def _req_with_user(user):
    req = RequestFactory().get("/")
    req.user = user
    return req


def test_default_returns_none_for_anonymous():
    user = MagicMock(is_authenticated=False)
    assert resolvers.default(_req_with_user(user)) is None


def test_default_returns_none_when_no_request_user():
    req = RequestFactory().get("/")
    assert resolvers.default(req) is None


def test_default_returns_first_membership_tenant():
    tenant = object()
    membership = MagicMock(tenant=tenant)
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value.first.return_value = membership
    user = MagicMock(is_authenticated=True, tenant_memberships=qs)
    assert resolvers.default(_req_with_user(user)) is tenant


def test_default_returns_none_when_no_memberships():
    qs = MagicMock()
    qs.select_related.return_value.order_by.return_value.first.return_value = None
    user = MagicMock(is_authenticated=True, tenant_memberships=qs)
    assert resolvers.default(_req_with_user(user)) is None


def test_load_configured_returns_default_when_unset():
    resolvers._cached_resolver = None
    with override_settings(WIREGRAPH={}):
        assert resolvers.load_configured() is resolvers.default


def test_load_configured_honors_override():
    resolvers._cached_resolver = None
    dotted = "tests.test_resolvers._custom_resolver"
    with override_settings(WIREGRAPH={"TENANT_RESOLVER": dotted}):
        resolved = resolvers.load_configured()
        assert resolved is _custom_resolver


def test_cache_invalidated_on_setting_change():
    resolvers._cached_resolver = None
    with override_settings(WIREGRAPH={}):
        first = resolvers.load_configured()
    with override_settings(
        WIREGRAPH={"TENANT_RESOLVER": "tests.test_resolvers._custom_resolver"}
    ):
        second = resolvers.load_configured()
    assert first is not second
    assert second is _custom_resolver


def _custom_resolver(request):
    return "custom-tenant"
