"""Presidio-backed deep NLP PII scanner (framework-agnostic).

Lazy-imports ``presidio_analyzer`` so the core package stays usable without
the extra. Hosts run this asynchronously (e.g. via Celery in the Django
integration — see ``wiregraph_apps.detection.tasks``).

Install with::

    pip install wiregraph[presidio]
    python -m spacy download en_core_web_lg
"""

from __future__ import annotations

from typing import Iterable

from wiregraph_core.types import Match


class PresidioUnavailable(RuntimeError):
    """Raised when Presidio is requested but the optional extra isn't installed."""


# Presidio entity_type -> WireGraph asset_name. Presidio entities we don't
# explicitly map are passed through lowercased (covers forward-compat for
# recognizers users plug in themselves).
_ENTITY_MAP = {
    "PERSON": "person_name",
    "LOCATION": "address",
    "PHONE_NUMBER": "phone",
    "EMAIL_ADDRESS": "email",
    "CREDIT_CARD": "credit_card",
    "IBAN_CODE": "iban",
    "US_SSN": "ssn",
    "US_PASSPORT": "passport",
    "US_DRIVER_LICENSE": "drivers_license",
    "IP_ADDRESS": "ip_address",
    "MEDICAL_LICENSE": "medical_license",
    "NRP": "nationality",
    "CRYPTO": "crypto_wallet",
}

# Presidio entities we suppress entirely. URL is noisy: it fires on email
# domains, CDN/media links, map links, and any domain.tld substring in
# descriptions — none of which are PII in typical threat models. DATE_TIME
# is dropped for the same reason: bare timestamps and durations ("10:15 UTC",
# "42 seconds") are not PII on their own, and structured dates that matter
# (DOB) are caught by the regex layer in context.
_DROPPED_ENTITIES = frozenset({"URL", "DATE_TIME"})


def _import_analyzer():
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore
    except ImportError as e:
        raise PresidioUnavailable(
            "ENABLE_PRESIDIO is True but presidio-analyzer is not installed. "
            "Install with `pip install wiregraph[presidio]` and "
            "`python -m spacy download en_core_web_lg`."
        ) from e
    return AnalyzerEngine


class PresidioScanner:
    def __init__(self, language: str = "en", min_score: float = 0.4):
        self.language = language
        self.min_score = min_score
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            AnalyzerEngine = _import_analyzer()
            self._engine = AnalyzerEngine()
        return self._engine

    def scan(self, text: str) -> list[Match]:
        if not text:
            return []
        engine = self._get_engine()
        results = engine.analyze(text=text, language=self.language)
        matches: list[Match] = []
        for r in results:
            if r.score < self.min_score:
                continue
            if r.entity_type in _DROPPED_ENTITIES:
                continue
            asset_name = _ENTITY_MAP.get(r.entity_type, r.entity_type.lower())
            matches.append(
                Match(
                    asset_name=asset_name,
                    start=r.start,
                    end=r.end,
                    value=text[r.start:r.end],
                    confidence=float(r.score),
                )
            )
        return matches


def dedupe_against(
    presidio_matches: Iterable[Match], regex_matches: Iterable[Match]
) -> list[Match]:
    """Drop Presidio matches whose span overlaps a regex match for the same asset.

    Regex matches are high-precision; prefer them when both layers fire on the
    same span. Different-asset overlaps are kept.
    """
    regex_spans: dict[str, list[tuple[int, int]]] = {}
    for m in regex_matches:
        regex_spans.setdefault(m.asset_name, []).append((m.start, m.end))

    kept: list[Match] = []
    for pm in presidio_matches:
        spans = regex_spans.get(pm.asset_name, ())
        if any(s < pm.end and pm.start < e for s, e in spans):
            continue
        kept.append(pm)
    return kept
