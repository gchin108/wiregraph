from django.contrib import admin

from .models import ProcessingActivity, ShadowDecisionCounter


@admin.register(ProcessingActivity)
class ProcessingActivityAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "legal_basis", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name",)
    filter_horizontal = ("data_assets", "external_services")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ShadowDecisionCounter)
class ShadowDecisionCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "tenant", "outcome", "shadow_alert_level", "count")
    list_filter = ("tenant", "day", "outcome", "shadow_alert_level")
    ordering = ("-day", "tenant_id")
    readonly_fields = ("id", "tenant", "day", "outcome", "shadow_alert_level", "count", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
