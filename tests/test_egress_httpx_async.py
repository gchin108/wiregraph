from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from wiregraph_apps.common.tenancy import reset_current_tenant, set_current_tenant
from wiregraph_apps.detection.models import DataEvent
from wiregraph_apps.egress import interceptor
from wiregraph_apps.egress.models import ExternalService
from tests.fixtures.factories import TenantFactory


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def tenant(db):
    return TenantFactory()


@pytest.fixture
def tenant_ctx(tenant):
    token = set_current_tenant(tenant)
    try:
        yield tenant
    finally:
        reset_current_tenant(token)


@pytest.fixture
def with_patch(settings):
    settings.WIREGRAPH = {"ENABLE_EGRESS_TRACKING": True, "DISABLE_EGRESS_PATCHING": False}
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as router:
        router.route(method="POST").respond(200)
        installed = interceptor.install_egress_patches()
        assert "httpx_async" in installed
        try:
            yield
        finally:
            interceptor.uninstall_egress_patches()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_httpx_async_records_external_service_and_pii_event(tenant_ctx, with_patch):
    async def go():
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}'
            )

    asyncio.run(go())

    service = ExternalService.objects.get(tenant=tenant_ctx, domain="api.openai.com")
    assert service.first_seen_at is not None

    event = DataEvent.objects.get(tenant=tenant_ctx, direction="egress")
    assert event.external_service_id == service.id
    assert event.data_asset.name == "email"
    assert event.endpoint == "/v1/chat"
    assert event.method == "POST"


def test_httpx_async_tenant_contextvar_propagates_across_await(tenant, with_patch):
    """ContextVar tenant set before asyncio.run propagates into the async call."""

    async def go():
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}'
            )

    token = set_current_tenant(tenant)
    try:
        asyncio.run(go())
    finally:
        reset_current_tenant(token)

    assert DataEvent.objects.filter(tenant=tenant, direction="egress").count() == 1


def test_httpx_async_internal_header_skips_interception(tenant_ctx, with_patch):
    async def go():
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://hooks.slack.com/svc",
                content=b'{"email": "a@b.com"}',
                headers={"X-Wiregraph-Internal": "1"},
            )

    asyncio.run(go())

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_httpx_async_no_current_tenant_skips(db, with_patch):
    async def go():
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.openai.com/v1/chat", content=b'{"email": "a@b.com"}'
            )

    asyncio.run(go())

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()
