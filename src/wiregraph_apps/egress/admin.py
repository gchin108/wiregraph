from django.contrib import admin

from .models import ExternalService


@admin.register(ExternalService)
class ExternalServiceAdmin(admin.ModelAdmin):
    list_display = ("domain", "name", "tenant", "first_seen_at", "last_seen_at")
    search_fields = ("domain", "name")
    list_filter = ("tenant",)
    readonly_fields = ("id", "created_at", "updated_at")
