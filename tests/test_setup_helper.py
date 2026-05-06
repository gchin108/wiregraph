from wiregraph.setup import DJANGO_AUTH, JWT_AUTH, PII_DETECTION, setup


def test_empty_list_appends_middleware():
    result = setup([])
    assert result == [JWT_AUTH, PII_DETECTION]


def test_inserts_after_django_auth():
    middleware = [
        "django.middleware.security.SecurityMiddleware",
        DJANGO_AUTH,
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    result = setup(middleware)
    auth_idx = result.index(DJANGO_AUTH)
    assert result[auth_idx + 1] == JWT_AUTH
    assert result[auth_idx + 2] == PII_DETECTION


def test_idempotent():
    middleware = [DJANGO_AUTH]
    once = setup(middleware)
    twice = setup(once)
    assert once == twice


def test_moves_existing_entries_to_correct_position():
    middleware = [
        PII_DETECTION,  # intentionally out of order
        DJANGO_AUTH,
        JWT_AUTH,  # intentionally out of order
    ]
    result = setup(middleware)
    assert result == [DJANGO_AUTH, JWT_AUTH, PII_DETECTION]


def test_no_django_auth_appends_to_end():
    middleware = ["django.middleware.security.SecurityMiddleware"]
    result = setup(middleware)
    assert result[-2:] == [JWT_AUTH, PII_DETECTION]


def test_does_not_mutate_input():
    middleware = [DJANGO_AUTH]
    before = list(middleware)
    setup(middleware)
    assert middleware == before


def test_include_jwt_false_omits_jwt_auth():
    result = setup([DJANGO_AUTH], include_jwt=False)
    assert JWT_AUTH not in result
    assert result == [DJANGO_AUTH, PII_DETECTION]


def test_include_jwt_false_strips_existing_jwt_entry():
    # If a consumer flips include_jwt=False but JWT_AUTH is still in their
    # list (e.g. left over from a previous DRF install), it must be removed.
    result = setup([DJANGO_AUTH, JWT_AUTH], include_jwt=False)
    assert JWT_AUTH not in result


def test_include_jwt_true_forces_inclusion():
    result = setup([DJANGO_AUTH], include_jwt=True)
    assert result == [DJANGO_AUTH, JWT_AUTH, PII_DETECTION]


def test_include_jwt_default_auto_detects(monkeypatch):
    # When DRF is unavailable, the default (None) must skip JWT_AUTH.
    monkeypatch.setattr(
        "wiregraph._drf.drf_available", lambda: False, raising=True
    )
    result = setup([DJANGO_AUTH])
    assert JWT_AUTH not in result
    assert PII_DETECTION in result


def test_include_jwt_default_includes_when_drf_available(monkeypatch):
    monkeypatch.setattr(
        "wiregraph._drf.drf_available", lambda: True, raising=True
    )
    result = setup([DJANGO_AUTH])
    assert result == [DJANGO_AUTH, JWT_AUTH, PII_DETECTION]
