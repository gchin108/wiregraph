from django.db import models

from wiregraph_apps.common.models import TenantScopedModel
from wiregraph_apps.constants import OUTCOME_CHOICES


class ProcessingActivity(TenantScopedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    legal_basis = models.CharField(
        max_length=255,
        blank=True,
        help_text="GDPR Article 6 legal basis — user-enriched",
    )
    data_assets = models.ManyToManyField(
        "wiregraph_detection.DataAsset",
        blank=True,
        related_name="processing_activities",
    )
    external_services = models.ManyToManyField(
        "wiregraph_egress.ExternalService",
        blank=True,
        related_name="processing_activities",
    )
    retention_period = models.CharField(
        max_length=255,
        blank=True,
        help_text="Data retention period — user-enriched",
    )
    dpo_contact = models.CharField(
        max_length=255,
        blank=True,
        help_text="Data Protection Officer contact — user-enriched",
    )

    class Meta(TenantScopedModel.Meta):
        verbose_name = "Processing Activity"
        verbose_name_plural = "Processing Activities"

    def __str__(self):
        return self.name


class ShadowDecisionCounter(TenantScopedModel):
    """Daily rollup of shadow-mode classifications (proposal §9.2).

    Counts events bucketed by ``(tenant, day, outcome, shadow_alert_level)`` so
    the noise-delta between legacy and new-policy alerting can be answered in
    one query even after ``DataEvent`` retention purges the underlying rows.
    """

    day = models.DateField(help_text="UTC date the classified event belongs to.")
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    shadow_alert_level = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    count = models.PositiveIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "day", "outcome", "shadow_alert_level")]
        indexes = [
            models.Index(fields=["tenant", "day"]),
        ]
        verbose_name = "Shadow Decision Counter"
        verbose_name_plural = "Shadow Decision Counters"

    def __str__(self):
        return f"{self.day} {self.outcome}→{self.shadow_alert_level}: {self.count}"


class EscalationCounter(TenantScopedModel):
    """Daily count of suspicious→prohibited escalations (proposal §5).

    Feeds the shadow report's ``suspicious_escalated_total`` metric which is
    how ``ESCALATION_SUSPICIOUS_COUNT`` gets calibrated from real traffic.
    """

    day = models.DateField(help_text="UTC date the escalation fired on.")
    count = models.PositiveIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "day")]
        indexes = [models.Index(fields=["tenant", "day"])]
        verbose_name = "Escalation Counter"
        verbose_name_plural = "Escalation Counters"

    def __str__(self):
        return f"{self.day}: {self.count}"


class AlertDigestEntry(TenantScopedModel):
    """Daily rollup for ``acceptable`` events (proposal §5 digest bucket).

    One row per ``(tenant, day, outcome, asset_name, service_domain)``; callers
    drive delivery via ``GET /api/v1/reporting/digest/``.
    """

    day = models.DateField()
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    asset_name = models.CharField(max_length=64)
    service_domain = models.CharField(max_length=255, blank=True)
    count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta(TenantScopedModel.Meta):
        unique_together = [
            ("tenant", "day", "outcome", "asset_name", "service_domain"),
        ]
        indexes = [models.Index(fields=["tenant", "day"])]
        verbose_name = "Alert Digest Entry"
        verbose_name_plural = "Alert Digest Entries"

    def __str__(self):
        return (
            f"{self.day} {self.outcome} {self.asset_name}→{self.service_domain}: "
            f"{self.count}"
        )
