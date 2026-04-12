from django.contrib import admin

from .models import DataAsset, DataEvent


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
