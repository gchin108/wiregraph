from django.db import models

from wiregraph_apps.common.models import TenantScopedModel
from wiregraph_apps.constants import (
    ALLOWLIST_SOURCE_CHOICES,
    DETECTION_METHOD_CHOICES,
    DIRECTION_CHOICES,
    OUTCOME_CHOICES,
    SENSITIVITY_CHOICES,
)


class DataAsset(TenantScopedModel):
    name = models.CharField(max_length=255, help_text="Machine-readable name, e.g. 'email_address'")
    label = models.CharField(max_length=255, help_text="Human-readable label, e.g. 'Email Address'")
    sensitivity_level = models.CharField(max_length=20, choices=SENSITIVITY_CHOICES, default="medium")
    description = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "name")]
        verbose_name = "Data Asset"
        verbose_name_plural = "Data Assets"

    def __str__(self):
        return self.label


class DataEvent(TenantScopedModel):
    data_asset = models.ForeignKey(
        DataAsset,
        on_delete=models.CASCADE,
        related_name="events",
    )
    external_service = models.ForeignKey(
        "wiregraph_egress.ExternalService",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    endpoint = models.CharField(max_length=2048, help_text="Request path, e.g. '/api/users/'")
    method = models.CharField(max_length=10, help_text="HTTP method, e.g. 'GET', 'POST'")
    detection_method = models.CharField(max_length=20, choices=DETECTION_METHOD_CHOICES)
    redacted_snippet = models.TextField(
        blank=True,
        help_text="Redacted or hashed PII context — never stores raw PII",
    )
    confidence = models.FloatField(
        default=1.0,
        help_text="Detection confidence score (0.0 to 1.0)",
    )
    match_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of matches coalesced into this event (per asset per request)",
    )
    request_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional correlation ID for grouping events from a single request",
    )
    timestamp = models.DateTimeField(help_text="When the PII was observed")
    outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default="expected",
        help_text="Deterministic classification of (asset, sink) — see detection.classifier.",
    )
    decision_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Machine-parseable 'namespace:detail' reason emitted by the classifier.",
    )

    class Meta(TenantScopedModel.Meta):
        verbose_name = "Data Event"
        verbose_name_plural = "Data Events"
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["tenant", "data_asset"]),
            models.Index(fields=["tenant", "direction"]),
        ]

    def __str__(self):
        return f"{self.data_asset} — {self.direction} @ {self.endpoint}"


class AllowlistRule(TenantScopedModel):
    asset_name = models.CharField(
        max_length=255,
        help_text="DataAsset.name to suppress, e.g. 'email'. Must match a detector asset name.",
    )
    endpoint_prefix = models.CharField(
        max_length=2048,
        blank=True,
        help_text="Optional endpoint path prefix. Empty string matches all endpoints.",
    )
    domain = models.CharField(
        max_length=255,
        blank=True,
        help_text="Exact host match, e.g. 'api.stripe.com'.",
    )
    domain_suffix = models.CharField(
        max_length=255,
        blank=True,
        help_text="Suffix host match, e.g. '.stripe.com' or 'stripe.com'.",
    )
    source = models.CharField(
        max_length=20,
        choices=ALLOWLIST_SOURCE_CHOICES,
        default="manual",
        help_text="How this rule was created — 'manual' from API/admin, 'feedback' from user verdicts.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable rationale, e.g. 'Login form — email is expected'.",
    )

    class Meta(TenantScopedModel.Meta):
        unique_together = [
            ("tenant", "asset_name", "endpoint_prefix", "domain", "domain_suffix"),
        ]
        verbose_name = "Allowlist Rule"
        verbose_name_plural = "Allowlist Rules"
        indexes = [
            models.Index(fields=["tenant", "asset_name"]),
        ]

    def __str__(self):
        scope = self.endpoint_prefix or "*"
        return f"{self.asset_name} @ {scope}"
