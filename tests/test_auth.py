import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.fixtures.factories import UserFactory


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory(username="alice")


def _obtain(client, username="alice", password="pw"):
    return client.post(
        "/api/v1/auth/token/",
        {"username": username, "password": password},
        format="json",
    )


def test_obtain_token_returns_access_and_refresh(api_client, user):
    response = _obtain(api_client)
    assert response.status_code == 200
    body = response.json()
    assert "access" in body
    assert "refresh" in body


def test_refresh_rotation_invalidates_old_refresh(api_client, user):
    tokens = _obtain(api_client).json()
    first_refresh = tokens["refresh"]

    rotated = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": first_refresh},
        format="json",
    )
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh"]
    assert new_refresh != first_refresh

    replay = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": first_refresh},
        format="json",
    )
    assert replay.status_code == 401


def test_auth_throttle_blocks_after_five_attempts(api_client):
    for _ in range(5):
        _obtain(api_client, username="nobody", password="wrong")
    blocked = _obtain(api_client, username="nobody", password="wrong")
    assert blocked.status_code == 429
