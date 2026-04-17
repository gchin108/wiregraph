"""Realistic payload integration tests.

Verifies the scanner correctly identifies every PII field embedded in
production-shaped request bodies, using the shared ``payloads.json``
fixture."""

import json
from pathlib import Path

import pytest

from wiregraph_apps.detection.regex_scanner import RegexScanner


FIXTURE = Path(__file__).parent / "fixtures" / "payloads.json"


@pytest.fixture(scope="module")
def payloads():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def scanner():
    return RegexScanner()


@pytest.mark.parametrize(
    "payload_name,expected",
    [
        ("signup", {"email", "phone_us"}),
        ("checkout", {"credit_card", "email", "ipv4"}),
        ("profile", {"email", "ssn"}),
        ("webhook", {"ipv6", "email"}),
    ],
)
def test_payload_detects_expected_assets(scanner, payloads, payload_name, expected):
    text = json.dumps(payloads[payload_name])
    found = {m.asset_name for m in scanner.scan(text)}
    assert expected.issubset(found), f"missing {expected - found} in {payload_name}"
