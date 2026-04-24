from django.contrib import admin

from .models import ExternalService, SinkCatalogOverride


@admin.register(ExternalService)
class ExternalServiceAdmin(admin.ModelAdmin):
    list_display = ("domain", "name", "tenant", "first_seen_at", "last_seen_at")
    search_fields = ("domain", "name")
    list_filter = ("tenant",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SinkCatalogOverride)
class SinkCatalogOverrideAdmin(admin.ModelAdmin):
    list_display = ("domain_suffix", "tenant", "trust_tier", "category")
    search_fields = ("domain_suffix", "display_name")
    list_filter = ("tenant", "trust_tier")
    readonly_fields = ("id", "created_at", "updated_at")
