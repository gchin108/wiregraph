"""End-to-end detection accuracy harness.

Measures precision/recall of the regex + custom-pattern scanner against the
curated fixtures in ``tests/fixtures/pii_samples.py`` and (optionally) the
Presidio scanner against ``tests/fixtures/presidio_payloads.py``.

Thresholds are conservative so the suite catches real regressions without
flaking on Presidio model variance.
"""

from __future__ import annotations

import pytest

from wiregraph_apps.detection.regex_scanner import RegexScanner
from tests.fixtures.pii_samples import SAMPLES


def _regex_metrics():
    scanner = RegexScanner(custom_patterns=[])
    tp = fn = fp = 0
    for asset, data in SAMPLES.items():
        for text in data["positives"]:
            matches = {m.asset_name for m in scanner.scan(text)}
            if asset in matches:
                tp += 1
            else:
                fn += 1
        for text in data["negatives"]:
            matches = {m.asset_name for m in scanner.scan(text)}
            if asset in matches:
                fp += 1
    return tp, fn, fp


def test_regex_recall_threshold():
    tp, fn, _ = _regex_metrics()
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    assert recall >= 0.95, f"regex recall {recall:.2f} dropped below 0.95"


def test_regex_false_positive_ceiling():
    _, _, fp = _regex_metrics()
    assert fp == 0, f"regex produced {fp} false positives on curated negatives"


def test_custom_patterns_precision():
    scanner = RegexScanner(custom_patterns=[
        {"name": "emp_id", "regex": r"\bEMP-\d{6}\b", "confidence": 0.85},
    ])
    positives = ["user EMP-000123 logged in", "ticket EMP-999999"]
    negatives = ["EMP-12 too short", "EMPLOYEE number lookup", "random text"]

    tp = sum(1 for t in positives if any(m.asset_name == "emp_id" for m in scanner.scan(t)))
    fp = sum(1 for t in negatives if any(m.asset_name == "emp_id" for m in scanner.scan(t)))
    assert tp == len(positives)
    assert fp == 0


# ---------------------------------------------------------------------------
# Presidio — only runs when the extra is installed.
# ---------------------------------------------------------------------------

try:
    import presidio_analyzer  # noqa: F401

    _HAS_PRESIDIO = True
except ImportError:
    _HAS_PRESIDIO = False

requires_presidio = pytest.mark.skipif(
    not _HAS_PRESIDIO, reason="presidio extra not installed"
)


@requires_presidio
def test_presidio_recall_on_labeled_set():
    from wiregraph_apps.detection.presidio_scanner import PresidioScanner
    from tests.fixtures.presidio_payloads import LABELED

    scanner = PresidioScanner(min_score=0.5)
    hits = 0
    total = 0
    for text, expected in LABELED:
        detected = {m.asset_name for m in scanner.scan(text)}
        total += len(expected)
        hits += len(expected & detected)
    recall = hits / total if total else 0.0
    assert recall >= 0.6, f"presidio recall {recall:.2f} below 0.6"


@requires_presidio
def test_presidio_false_positive_rate_on_negatives():
    from wiregraph_apps.detection.presidio_scanner import PresidioScanner
    from tests.fixtures.presidio_payloads import NEGATIVES

    scanner = PresidioScanner(min_score=0.6)
    flagged = sum(1 for t in NEGATIVES if scanner.scan(t))
    fp_rate = flagged / len(NEGATIVES)
    assert fp_rate <= 0.25, f"presidio FP rate {fp_rate:.2f} above 0.25 on infra strings"
