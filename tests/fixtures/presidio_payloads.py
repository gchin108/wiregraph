"""Labeled payloads for Presidio accuracy measurement.

Each entry is a (text, expected_assets) pair. ``expected_assets`` names map to
WireGraph asset names (see ``presidio_scanner._ENTITY_MAP``). Negatives are
plain strings expected to produce no high-confidence PII matches.
"""

from __future__ import annotations

LABELED = [
    ("Jane Doe lives at 221B Baker Street, London.",
     {"person_name", "address"}),
    ("Please contact Dr. Alice Smith about the appointment.",
     {"person_name"}),
    ("Her mobile is +44 20 7946 0958.",
     {"phone"}),
    ("IBAN: DE89 3704 0044 0532 0130 00 for the wire transfer.",
     {"iban"}),
    ("Patient Maria Garcia was admitted on 2025-03-14.",
     {"person_name"}),
    ("Send the package to 1600 Pennsylvania Avenue NW, Washington DC.",
     {"address"}),
]

NEGATIVES = [
    "The server returned a 500 error; please retry.",
    "Kubernetes cluster scaled from 3 to 5 nodes.",
    "The build finished in 42 seconds with no warnings.",
    "Deploy succeeded to staging at 10:15 UTC.",
    "Migration 0042_user_schema applied cleanly.",
    "Cache hit ratio dropped to 0.78 after the rollout.",
    "Worker pool exhausted; retrying with backoff.",
    "GET /api/v1/health returned 200 in 12ms.",
    "Pod evicted due to memory pressure on node-7.",
    "CI pipeline finished with 3 warnings and 0 errors.",
    "Redis broker reconnected after a transient timeout.",
    "Feature flag rollout_v2 enabled for cohort B.",
    "Postgres replica lag is 240ms over the last minute.",
    "Background task queue drained in under a second.",
]
