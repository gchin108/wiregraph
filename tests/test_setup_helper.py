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
