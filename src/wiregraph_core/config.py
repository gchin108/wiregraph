"""Runtime configuration for the detection core.

Mirrors the subset of ``WIREGRAPH`` settings consumed by the extracted
pure-Python modules. Hosts (Django today) build a :class:`DetectionConfig`
from their own settings and pass it in — core code never reaches back into
``django.conf.settings``.

Defaults match ``wiregraph_apps.common.conf.DEFAULTS`` so a freshly
constructed ``DetectionConfig()`` behaves like an unconfigured install.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DetectionConfig:
    # Scanner
    redact_strategy: str = "hash"
    custom_patterns: list[dict] = field(default_factory=list)

    # Classifier
    llm_policy: str = "strict"  # "strict" | "relaxed"
    confidence_low: float = 0.5
    confidence_high: float = 0.9

    # Sinks (overrides merged on top of the builtin catalog by the host)
    sink_overrides: dict = field(default_factory=dict)

    # Dedup
    dedup_window_prohibited_seconds: int = 300
    dedup_window_suspicious_seconds: int = 3600

    # Escalation
    escalation_suspicious_count: int = 10
    escalation_window_seconds: int = 86400

    # Shadow mode
    shadow_mode: bool = False

    @property
    def confidence_thresholds(self) -> tuple[float, float]:
        return self.confidence_low, self.confidence_high

    @property
    def dedup_windows(self) -> tuple[int, int]:
        return (
            self.dedup_window_prohibited_seconds,
            self.dedup_window_suspicious_seconds,
        )
