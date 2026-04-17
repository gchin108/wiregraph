import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import responses as responses_lib  # noqa: E402


@__import__("pytest").fixture
def mock_responses():
    """Activate the ``responses`` library to intercept all outbound HTTP calls.

    Any ``requests``-based call that doesn't match a registered URL will raise
    ``ConnectionError``, preventing accidental network access in tests.

    Usage in tests::

        def test_something(mock_responses):
            mock_responses.post(
                "https://api.openai.com/v1/chat/completions",
                json={"choices": [{"message": {"content": "hi"}}]},
            )
            # ... code that calls the endpoint ...
    """
    with responses_lib.RequestsMock() as rsps:
        yield rsps
