from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AssistantLog, Hint


@admin.register(AssistantLog)
class AssistantLogAdmin(ModelAdmin):
    list_display = ["created_at", "user", "kind", "mission", "success", "duration_ms", "error"]
    list_filter = ["kind", "success", "created_at"]
    search_fields = ["user__email", "user__nickname"]

    # Журналът се пише само от кода.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Hint)
class HintAdmin(ModelAdmin):
    list_display = ["created_at", "student", "mission", "text"]
    search_fields = ["student__nickname", "mission__title"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
