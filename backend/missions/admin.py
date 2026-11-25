from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import Claim, DeadlineExtension, EvidenceFile, Mission, MissionFile


class EvidenceFileInline(TabularInline):
    """Файловете към заявката. Администраторът може да изтрие неподходящ файл."""

    model = EvidenceFile
    fields = ["preview", "kind", "size_kb", "uploaded_at"]
    readonly_fields = fields
    extra = 0
    verbose_name_plural = "файлове към доказателството"

    @admin.display(description="файл")
    def preview(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', obj.get_absolute_url(),
                           obj.original_name)

    @admin.display(description="размер")
    def size_kb(self, obj):
        return f"{max(1, obj.size // 1024)} KB"

    def has_add_permission(self, request, obj=None):
        return False


class MissionFileInline(EvidenceFileInline):
    model = MissionFile
    verbose_name_plural = "файлове към мисията"


@admin.register(Mission)
class MissionAdmin(ModelAdmin):
    list_display = ["title", "kind", "guild", "subject", "xp", "deadline", "is_active", "is_group", "hints_allowed", "created_by"]
    list_filter = ["kind", "guild", "is_active", "is_group", "hints_allowed"]
    filter_horizontal = ["reviewers", "school_classes"]
    inlines = [MissionFileInline]
    search_fields = ["title", "description"]
    date_hierarchy = "deadline"


@admin.register(DeadlineExtension)
class DeadlineExtensionAdmin(ModelAdmin):
    """Администраторът може да даде срок и безплатно, напр. при болест."""

    list_display = ["mission", "student", "until", "created_at"]
    search_fields = ["mission__title", "student__nickname", "student__email"]
    fields = ["mission", "student", "until", "purchase"]
    readonly_fields = ["purchase"]


@admin.register(Claim)
class ClaimAdmin(ModelAdmin):
    list_display = ["mission", "student", "status", "submitted_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status", "mission__guild"]
    search_fields = ["mission__title", "student__nickname", "student__email"]
    # Потвърждаването става през правилата на играта (economy), не с ръчна промяна тук,
    # иначе XP няма да се начисли. Затова тези полета са само за четене.
    readonly_fields = ["status", "captain", "reviewed_by", "reviewed_at", "submitted_at"]
    inlines = [EvidenceFileInline]
