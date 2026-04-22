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
