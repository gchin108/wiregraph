import pytest

from core_apps.detection.regex_scanner import RegexScanner, _luhn_valid, redact
from tests.fixtures.pii_samples import SAMPLES


@pytest.fixture
def scanner():
    return RegexScanner()


@pytest.mark.parametrize(
    "asset,text",
    [(asset, t) for asset, data in SAMPLES.items() for t in data["positives"]],
)
def test_positives_detected(scanner, asset, text):
    matches = scanner.scan(text)
    assert any(m.asset_name == asset for m in matches), (
        f"{asset} not detected in {text!r}; got {matches}"
    )


@pytest.mark.parametrize(
    "asset,text",
    [(asset, t) for asset, data in SAMPLES.items() for t in data["negatives"]],
)
def test_negatives_not_detected(scanner, asset, text):
    matches = scanner.scan(text)
    assert not any(m.asset_name == asset for m in matches), (
        f"{asset} falsely detected in {text!r}; got {matches}"
    )


def test_luhn_valid_accepts_known_test_pans():
    assert _luhn_valid("4111111111111111")
    assert _luhn_valid("5500000000000004")


def test_luhn_valid_rejects_bad_checksum():
    assert not _luhn_valid("4111111111111112")
    assert not _luhn_valid("1234567890123456")


def test_scanner_finds_multiple_assets_in_one_blob(scanner):
    text = "Contact jane@example.com from 192.168.1.1; card 4111111111111111"
    assets = {m.asset_name for m in scanner.scan(text)}
    assert {"email", "ipv4", "credit_card"}.issubset(assets)


def test_scanner_empty_input(scanner):
    assert scanner.scan("") == []


def test_redact_hash_is_stable_and_non_reversible():
    a = redact("jane@example.com", "hash")
    b = redact("jane@example.com", "hash")
    assert a == b
    assert a.startswith("sha256:")
    assert "jane" not in a


def test_redact_mask_email():
    out = redact("jane@example.com", "mask")
    assert "jane" not in out
    assert "@" in out


def test_redact_mask_generic():
    out = redact("4111111111111111", "mask")
    assert "1111111111" not in out
    assert out[0] == "4" and out[-1] == "1"


def test_redact_truncate_short_and_long():
    assert redact("abc", "truncate") == "***"
    assert redact("jane@example.com", "truncate") == "jan...com"


def test_redact_unknown_strategy_raises():
    with pytest.raises(ValueError):
        redact("x", "bogus")
