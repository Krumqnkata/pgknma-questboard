from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from .legal_defaults import DEFAULTS
from .models import SitePage


@admin.register(SitePage)
class SitePageAdmin(ModelAdmin):
    """Двете страници са фиксирани: текстът им се сменя, но не се добавят и трият."""

    list_display = ["title", "slug", "updated_at"]
    fields = ["title", "content", "updated_at"]
    readonly_fields = ["updated_at"]
    actions = ["restore_default"]

    @admin.action(description="Върни началния текст на избраните страници")
    def restore_default(self, request, queryset):
        for page in queryset:
            page.title, page.content = DEFAULTS[page.slug]
            page.save()
        self.message_user(request, "Началният текст е върнат.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
