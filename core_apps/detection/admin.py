from django.contrib import admin

from core_apps.detection.allowlist import invalidate_tenant_rules

from .models import AllowlistRule, DataAsset, DataEvent


@admin.register(DataAsset)
class DataAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "sensitivity_level", "tenant", "created_at")
    list_filter = ("sensitivity_level", "tenant")
    search_fields = ("name", "label")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(DataEvent)
class DataEventAdmin(admin.ModelAdmin):
    list_display = (
        "data_asset",
        "direction",
        "endpoint",
        "method",
        "detection_method",
        "confidence",
        "timestamp",
    )
    list_filter = ("direction", "detection_method", "data_asset", "tenant")
    search_fields = ("endpoint", "request_id")
    readonly_fields = ("id", "redacted_snippet", "timestamp", "created_at", "updated_at")
    date_hierarchy = "timestamp"
    raw_id_fields = ("data_asset", "external_service")


@admin.register(AllowlistRule)
class AllowlistRuleAdmin(admin.ModelAdmin):
    list_display = ("asset_name", "endpoint_prefix", "tenant", "reason", "created_at")
    list_filter = ("tenant", "asset_name")
    search_fields = ("asset_name", "endpoint_prefix", "reason")
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_tenant_rules(obj.tenant)

    def delete_model(self, request, obj):
        tenant = obj.tenant
        super().delete_model(request, obj)
        invalidate_tenant_rules(tenant)
