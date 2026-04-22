from django.db import models

from wiregraph_apps.common.models import TenantScopedModel
from wiregraph_apps.constants import SINK_CATEGORY_CHOICES, TRUST_TIER_CHOICES


class ExternalService(TenantScopedModel):
    domain = models.CharField(max_length=255, help_text="e.g. 'api.openai.com'")
    name = models.CharField(max_length=255, help_text="Human-readable name, e.g. 'OpenAI'")
    purpose = models.TextField(blank=True, help_text="User-annotated purpose of this service")
    first_seen_at = models.DateTimeField(help_text="When this service was first observed in traffic")
    last_seen_at = models.DateTimeField(help_text="When this service was last observed in traffic")
    category = models.CharField(
        max_length=32,
        choices=SINK_CATEGORY_CHOICES,
        default="unknown",
        help_text="Sink category populated from the sink catalog on first sight.",
    )
    accepts_assets = models.JSONField(
        default=list,
        blank=True,
        help_text="Asset names this sink is expected to receive, e.g. ['email','person_name'].",
    )
    trust_tier = models.CharField(
        max_length=16,
        choices=TRUST_TIER_CHOICES,
        default="unknown",
        help_text="How much trust the classifier grants this sink.",
    )

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "domain")]
        verbose_name = "External Service"
        verbose_name_plural = "External Services"

    def __str__(self):
        return f"{self.name} ({self.domain})"


class SinkCatalogOverride(TenantScopedModel):
    """Tenant-scoped override of a sink catalog entry.

    Matched by ``domain_suffix`` (longest wins) against outbound hosts. See
    ``wiregraph_apps.sinks.resolve_sink`` for resolution order.
    """

    domain_suffix = models.CharField(
        max_length=255,
        help_text="Suffix to match, e.g. 'stripe.com' or 'api.internal.corp'.",
    )
    category = models.CharField(
        max_length=32,
        choices=SINK_CATEGORY_CHOICES,
        default="unknown",
    )
    trust_tier = models.CharField(
        max_length=16,
        choices=TRUST_TIER_CHOICES,
        default="unknown",
    )
    accepts_assets = models.JSONField(
        default=list,
        blank=True,
        help_text="Empty list means 'use category default'; omit assets to accept nothing.",
    )
    display_name = models.CharField(max_length=255, blank=True)

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "domain_suffix")]
        verbose_name = "Sink Catalog Override"
        verbose_name_plural = "Sink Catalog Overrides"

    def __str__(self):
        return f"{self.domain_suffix} → {self.category}/{self.trust_tier}"
