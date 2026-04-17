from django.contrib import admin

from .models import ProcessingActivity


@admin.register(ProcessingActivity)
class ProcessingActivityAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "legal_basis", "created_at")
    list_filter = ("tenant",)
    search_fields = ("name",)
    filter_horizontal = ("data_assets", "external_services")
    readonly_fields = ("id", "created_at", "updated_at")
