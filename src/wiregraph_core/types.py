"""Core dataclasses shared by detection scanners and the classifier.

These are the wire types between framework-agnostic logic and any host
(Django middleware today, FastAPI tomorrow). Hosts resolve their
persistence-layer rows into these dataclasses before calling into core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Outcome = Literal["expected", "acceptable", "suspicious", "prohibited"]
AlertLevel = Literal["expected", "acceptable", "suspicious", "prohibited"]
SensitivityLevel = Literal["low", "medium", "high", "critical"]
TrustTier = Literal["trusted", "known", "unknown"]


@dataclass(frozen=True)
class Match:
    """A single detector hit inside a scanned text blob."""

    asset_name: str
    start: int
    end: int
    value: str
    confidence: float
    json_path: str | None = None


@dataclass(frozen=True)
class Asset:
    """Resolved data asset spec — what was detected."""

    name: str
    sensitivity_level: str  # SensitivityLevel; widened for forward-compat


@dataclass(frozen=True)
class Sink:
    """Resolved external service spec — where data is going."""

    domain: str
    category: str  # e.g. "llm", "payments", "internal", "unknown"
    trust_tier: str  # TrustTier; widened for forward-compat
    accepts_assets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RuleHit:
    """An allowlist rule matched — classification short-circuits to expected."""


@dataclass(frozen=True)
class Policy:
    llm_mode: str = "strict"  # "strict" | "relaxed"


@dataclass(frozen=True)
class FlowHistory:
    """Caller-supplied history facts the pure classifier needs.

    The host populates this from its own store (e.g. ``DataEvent.objects.filter(...)``
    in the Django adapter) before invoking :func:`classify`.
    """

    is_new_flow: bool = False


@dataclass(frozen=True)
class Decision:
    """The result of classifying one (asset, sink) flow."""

    outcome: Outcome
    reason: str  # "namespace:detail" — see REASON_PREFIXES
