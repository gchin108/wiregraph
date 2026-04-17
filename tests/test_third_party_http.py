"""Tests demonstrating ``responses`` library for mocking third-party HTTP APIs.

The ``mock_responses`` fixture (from conftest) activates request interception.
Any outbound ``requests`` call that doesn't match a registered URL raises
``ConnectionError``, so tests never hit real endpoints.
"""

from __future__ import annotations

import pytest
import requests

# -- OpenAI ------------------------------------------------------------------


class TestOpenAI:
    def test_chat_completion_response(self, mock_responses):
        """Mock an OpenAI chat completion and verify the parsed response."""
        mock_responses.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "id": "chatcmpl-abc123",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
            status=200,
        )

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Say hello"}],
            },
            headers={"Authorization": "Bearer sk-fake-key"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "Hello!"
        assert data["usage"]["total_tokens"] == 15

    def test_openai_rate_limit(self, mock_responses):
        """Simulate a 429 rate-limit response from OpenAI."""
        mock_responses.post(
            "https://api.openai.com/v1/chat/completions",
            json={"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
            status=429,
        )

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
        )

        assert resp.status_code == 429
        assert "rate_limit" in resp.json()["error"]["type"]

    def test_openai_server_error(self, mock_responses):
        """Simulate a 500 server error from OpenAI."""
        mock_responses.post(
            "https://api.openai.com/v1/chat/completions",
            json={"error": {"message": "Internal server error"}},
            status=500,
        )

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": []},
        )

        assert resp.status_code == 500


# -- Stripe ------------------------------------------------------------------


class TestStripe:
    def test_create_charge(self, mock_responses):
        mock_responses.post(
            "https://api.stripe.com/v1/charges",
            json={
                "id": "ch_1234",
                "object": "charge",
                "amount": 2000,
                "currency": "usd",
                "status": "succeeded",
            },
            status=200,
        )

        resp = requests.post(
            "https://api.stripe.com/v1/charges",
            data={"amount": 2000, "currency": "usd", "source": "tok_visa"},
            headers={"Authorization": "Bearer sk_test_fake"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "succeeded"


# -- Egress interceptor + responses -----------------------------------------


@pytest.mark.django_db
class TestEgressWithResponses:
    """Verify wiregraph's egress interceptor works on top of ``responses``.

    These tests require a running database (run via Docker).
    """

    @pytest.fixture
    def tenant(self, db):
        from tests.fixtures.factories import TenantFactory

        return TenantFactory()

    @pytest.fixture
    def tenant_ctx(self, tenant):
        from core_apps.common.tenancy import reset_current_tenant, set_current_tenant

        token = set_current_tenant(tenant)
        try:
            yield tenant
        finally:
            reset_current_tenant(token)

    @pytest.fixture
    def egress_enabled(self, settings, mock_responses):
        from core_apps.egress import interceptor

        settings.WIREGRAPH = {
            "ENABLE_EGRESS_TRACKING": True,
            "DISABLE_EGRESS_PATCHING": False,
        }
        assert interceptor.install_egress_patch()
        try:
            yield mock_responses
        finally:
            interceptor.uninstall_egress_patch()

    def test_egress_detects_pii_in_openai_call(self, tenant_ctx, egress_enabled):
        from core_apps.detection.models import DataEvent
        from core_apps.egress.models import ExternalService

        egress_enabled.post(
            "https://api.openai.com/v1/chat/completions",
            json={"choices": [{"message": {"content": "ok"}}]},
            status=200,
        )

        session = requests.Session()
        session.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "email is test@example.com"}],
            },
        )

        assert ExternalService.objects.filter(
            tenant=tenant_ctx, domain="api.openai.com"
        ).exists()
        events = DataEvent.objects.filter(tenant=tenant_ctx, direction="egress")
        assert events.count() >= 1
        assert events.first().data_asset.name == "email"

    def test_no_pii_no_event(self, tenant_ctx, egress_enabled):
        from core_apps.detection.models import DataEvent
        from core_apps.egress.models import ExternalService

        egress_enabled.post(
            "https://api.openai.com/v1/chat/completions",
            json={"choices": [{"message": {"content": "ok"}}]},
            status=200,
        )

        session = requests.Session()
        session.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]},
        )

        assert ExternalService.objects.filter(domain="api.openai.com").exists()
        assert not DataEvent.objects.filter(direction="egress").exists()


# -- Safety ------------------------------------------------------------------


class TestSafety:
    def test_unregistered_url_raises(self, mock_responses):
        """Unregistered URLs raise ConnectionError -- no accidental network calls."""
        with pytest.raises(requests.exceptions.ConnectionError):
            requests.get("https://unregistered.example.com/api")
