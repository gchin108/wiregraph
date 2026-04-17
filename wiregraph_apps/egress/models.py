from django.db import models

from wiregraph_apps.common.models import TenantScopedModel


class ExternalService(TenantScopedModel):
    domain = models.CharField(max_length=255, help_text="e.g. 'api.openai.com'")
    name = models.CharField(max_length=255, help_text="Human-readable name, e.g. 'OpenAI'")
    purpose = models.TextField(blank=True, help_text="User-annotated purpose of this service")
    first_seen_at = models.DateTimeField(help_text="When this service was first observed in traffic")
    last_seen_at = models.DateTimeField(help_text="When this service was last observed in traffic")

    class Meta(TenantScopedModel.Meta):
        unique_together = [("tenant", "domain")]
        verbose_name = "External Service"
        verbose_name_plural = "External Services"

    def __str__(self):
        return f"{self.name} ({self.domain})"
