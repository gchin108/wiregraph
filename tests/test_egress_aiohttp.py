from __future__ import annotations

import asyncio
import contextlib

import aiohttp
import pytest
from aioresponses import aioresponses

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


@pytest.fixture(autouse=True)
def egress_enabled(settings):
    settings.WIREGRAPH = {"ENABLE_EGRESS_TRACKING": True, "DISABLE_EGRESS_PATCHING": False}


@contextlib.contextmanager
def _mocked_and_patched():
    """aioresponses replaces ClientSession._request, so install our patch INSIDE."""
    with aioresponses() as m:
        installed = interceptor.install_egress_patches()
        assert "aiohttp" in installed
        try:
            yield m
        finally:
            interceptor.uninstall_egress_patches()


def test_aiohttp_records_external_service_and_pii_event_json(tenant_ctx):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://api.openai.com/v1/chat", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.openai.com/v1/chat", json={"email": "a@b.com"}
                )

    asyncio.run(go())

    service = ExternalService.objects.get(tenant=tenant_ctx, domain="api.openai.com")
    event = DataEvent.objects.get(tenant=tenant_ctx, direction="egress")
    assert event.external_service_id == service.id
    assert event.data_asset.name == "email"
    assert event.endpoint == "/v1/chat"
    assert event.method == "POST"


def test_aiohttp_form_data_dict(tenant_ctx):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://api.openai.com/v1/chat", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.openai.com/v1/chat", data={"email": "a@b.com"}
                )

    asyncio.run(go())

    assert DataEvent.objects.filter(direction="egress").count() == 1


def test_aiohttp_bytes_body(tenant_ctx):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://api.openai.com/v1/chat", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.openai.com/v1/chat", data=b'{"email": "a@b.com"}'
                )

    asyncio.run(go())

    assert DataEvent.objects.filter(direction="egress").count() == 1


def test_aiohttp_no_pii_still_touches_service(tenant_ctx):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://api.stripe.com/v1/charges", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.stripe.com/v1/charges", json={"amount": 100}
                )

    asyncio.run(go())

    assert ExternalService.objects.filter(domain="api.stripe.com").exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_aiohttp_internal_header_skips_interception(tenant_ctx):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://hooks.slack.com/svc", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://hooks.slack.com/svc",
                    json={"email": "a@b.com"},
                    headers={"X-Wiregraph-Internal": "1"},
                )

    asyncio.run(go())

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()


def test_aiohttp_no_current_tenant_skips(db):
    async def go():
        with _mocked_and_patched() as m:
            m.post("https://api.openai.com/v1/chat", status=200)
            async with aiohttp.ClientSession() as session:
                await session.post(
                    "https://api.openai.com/v1/chat", json={"email": "a@b.com"}
                )

    asyncio.run(go())

    assert not ExternalService.objects.exists()
    assert not DataEvent.objects.filter(direction="egress").exists()
