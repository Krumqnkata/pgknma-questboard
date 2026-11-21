from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from assistant_bridge.client import check_assistant_health

from .models import CoinTransaction, GameSettings, Level, Privilege, Purchase, XPTransaction


@admin.register(GameSettings)
class GameSettingsAdmin(ModelAdmin):
    """Една страница с всички правила на играта и настройките на асистента."""

    fieldsets = [
        ("Правила на играта", {"fields": [
            "xp_per_coin", "weekly_coin_limit", "carry_over_remainder",
            "week_start_day", "max_xp_per_mission",
        ]}),
        ("Асистент", {"fields": [
            "assistant_status", "assistant_enabled", "llm_provider", "llm_model", "assistant_daily_limit",
        ]}),
        (None, {"fields": ["updated_at"]}),
    ]
    readonly_fields = ["assistant_status", "updated_at"]

    @admin.display(description="състояние на услугата")
    def assistant_status(self, obj):
        """Пита услугата на асистента дали работи и показва зелено или червено."""
        ok, message = check_assistant_health()
        color = "#1a7f37" if ok else "#cf222e"
        return format_html('<strong style="color:{}">● {}</strong>', color, message)

    def changelist_view(self, request, extra_context=None):
        # Няма списък – отиваме направо на единствения ред с настройки.
        GameSettings.load()
        return redirect(reverse("admin:economy_gamesettings_change", args=[1]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Level)
class LevelAdmin(ModelAdmin):
    list_display = ["number", "min_xp", "title"]


@admin.register(Privilege)
class PrivilegeAdmin(ModelAdmin):
    list_display = ["name", "code", "price", "is_active"]
    list_editable = ["price", "is_active"]


class ReadOnlyLedgerAdmin(ModelAdmin):
    """
    Журналът на движенията се пише само от кода с правилата на играта.
    В admin може да се гледа и търси, но не и да се променя или трие.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(XPTransaction)
class XPTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ["created_at", "student", "amount", "reason", "created_by"]
    list_filter = ["created_at"]
    search_fields = ["student__nickname", "student__email", "reason"]


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ["created_at", "student", "amount", "kind", "reason", "created_by"]
    list_filter = ["kind", "created_at"]
    search_fields = ["student__nickname", "student__email", "reason"]


@admin.register(Purchase)
class PurchaseAdmin(ReadOnlyLedgerAdmin):
    list_display = ["purchased_at", "student", "privilege", "price_paid", "used_at", "marked_used_by"]
    list_filter = ["privilege", "used_at"]
    search_fields = ["student__nickname", "student__email"]
