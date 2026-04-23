from django.core.cache import cache

from wiregraph_apps.detection.dedup import should_emit


def setup_function(_):
    cache.clear()


def test_first_call_emits():
    assert should_emit(("t", "email", "api.stripe.com"), 60) is True


def test_second_call_within_window_suppressed():
    key = ("t", "email", "api.stripe.com")
    assert should_emit(key, 60) is True
    assert should_emit(key, 60) is False


def test_different_keys_independent():
    assert should_emit(("t", "email", "a.com"), 60) is True
    assert should_emit(("t", "email", "b.com"), 60) is True


def test_zero_window_disables_dedup():
    key = ("t", "email", "api.stripe.com")
    assert should_emit(key, 0) is True
    assert should_emit(key, 0) is True


def test_key_parts_order_matters():
    assert should_emit(("a", "b"), 60) is True
    assert should_emit(("b", "a"), 60) is True


def test_none_parts_handled():
    assert should_emit((None, "email", None), 60) is True
    assert should_emit((None, "email", None), 60) is False
