"""Curated PII fixtures for detection tests.

Each asset has ``positives`` (should be detected) and ``negatives`` (must not
be detected). Luhn-invalid credit card numbers live in ``negatives`` to prove
the Luhn gate works.
"""

SAMPLES = {
    "email": {
        "positives": [
            "jane.doe@example.com",
            "user+tag@sub.example.co.uk",
            "a_b-c.d@example.io",
        ],
        "negatives": [
            "not-an-email",
            "missing@tld",
            "@no-local.com",
        ],
    },
    "ssn": {
        "positives": [
            "123-45-6789",
            "555-12-3456",
        ],
        "negatives": [
            "000-12-3456",
            "666-12-3456",
            "900-12-3456",
            "123-00-6789",
            "123-45-0000",
            "12-345-6789",
        ],
    },
    "credit_card": {
        # Luhn-valid test numbers (industry standard sandbox PANs).
        "positives": [
            "4111111111111111",
            "5500 0000 0000 0004",
            "3400-0000-0000-009",
            "6011000000000004",
        ],
        # Luhn-invalid 16-digit numbers — must be rejected.
        "negatives": [
            "4111111111111112",
            "1234567890123456",
            "9999999999999999",
        ],
    },
    "phone_us": {
        "positives": [
            "(415) 555-2671",
            "415-555-2671",
            "+1 415.555.2671",
            "4155552671",
        ],
        "negatives": [
            "123-45-6789",
            "111-222-3333",
            "0000000000",
        ],
    },
    "ipv4": {
        "positives": [
            "192.168.1.1",
            "8.8.8.8",
            "255.255.255.255",
        ],
        "negatives": [
            "256.1.1.1",
            "999.999.999.999",
            "1.2.3",
        ],
    },
    "ipv6": {
        "positives": [
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "fe80:0000:0000:0000:0202:b3ff:fe1e:8329",
        ],
        "negatives": [
            "not:an:ipv6:addr",
            "2001:db8::1",  # compressed form — deliberately not supported for v1
        ],
    },
}
