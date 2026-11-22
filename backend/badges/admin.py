from django.contrib import admin, messages
from django.db.models import Count
from unfold.admin import ModelAdmin

from accounts.models import User

from .models import Badge, StudentBadge
from .services import award_badges


@admin.register(Badge)
class BadgeAdmin(ModelAdmin):
    list_display = ["name", "rule", "threshold", "guild", "is_active", "earned_by"]
    list_editable = ["is_active"]
    list_filter = ["rule", "is_active"]
    fields = ["name", "description", "icon", "rule", "threshold", "guild", "is_active", "order"]
    actions = ["award_to_everyone"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(earned_count=Count("awards"))

    @admin.display(description="получили", ordering="earned_count")
    def earned_by(self, obj):
        return obj.earned_count

    @admin.action(description="Раздай значките на учениците, които вече ги заслужават")
    def award_to_everyone(self, request, queryset):
        # Полезно, когато се добави нова значка: учениците, стигнали прага по-рано, също я получават.
        given = sum(len(award_badges(student)) for student in User.objects.filter(role=User.Role.STUDENT))
        self.message_user(request, f"Раздадени значки: {given}.", messages.SUCCESS)


@admin.register(StudentBadge)
class StudentBadgeAdmin(ModelAdmin):
    """Само за преглед – значките се дават от самата игра."""

    list_display = ["student", "badge", "awarded_at"]
    list_filter = ["badge"]
    search_fields = ["student__nickname", "student__email"]
    list_select_related = ["student", "badge"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
