from django.contrib import admin

from .models import Claim, Mission


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ["title", "guild", "xp", "deadline", "is_active", "hints_allowed", "created_by"]
    list_filter = ["guild", "is_active", "hints_allowed"]
    search_fields = ["title", "description"]
    date_hierarchy = "deadline"


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ["mission", "student", "status", "submitted_at", "reviewed_by", "reviewed_at"]
    list_filter = ["status", "mission__guild"]
    search_fields = ["mission__title", "student__nickname", "student__email"]
    # Потвърждаването става през правилата на играта (economy), не с ръчна промяна тук,
    # иначе XP няма да се начисли. Затова тези полета са само за четене.
    readonly_fields = ["status", "reviewed_by", "reviewed_at", "submitted_at"]
