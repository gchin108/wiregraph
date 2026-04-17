from django.db import models

from wiregraph_apps.common.models import TenantScopedModel


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
