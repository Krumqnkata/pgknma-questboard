from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    """Само за преглед – известията се създават от самата игра."""

    list_display = ["user", "kind", "text", "created_at", "read_at"]
    list_filter = ["kind", "created_at"]
    search_fields = ["user__email", "user__nickname", "text"]
    list_select_related = ["user"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
