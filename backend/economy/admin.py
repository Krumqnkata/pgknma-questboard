from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action

from assistant_bridge.client import check_assistant_health, check_model

from .models import CoinTransaction, CoinWeek, GameSettings, Level, Privilege, Purchase, Sponsor, XPTransaction


@admin.register(GameSettings)
class GameSettingsAdmin(ModelAdmin):
    """Една страница с всички правила на играта и настройките на асистента."""

    fieldsets = [
        ("Правила на играта", {"fields": [
            "xp_per_coin", "weekly_coin_limit", "carry_over_remainder",
            "week_start_day", "max_xp_per_mission", "max_xp_per_homework",
        ]}),
        ("Асистент", {"fields": [
            "assistant_status", "assistant_enabled", "llm_provider", "llm_model", "assistant_daily_limit",
        ]}),
        ("Училище", {"fields": ["school_name", "school_logo", "contact_email"]}),
        ("Бонус XP от учител", {"fields": ["bonus_max_xp", "bonus_weekly_xp", "undo_days"]}),
        ("Доказателства", {"fields": ["evidence_max_files", "evidence_max_mb"]}),
        ("Псевдоними", {"fields": ["nickname_change_days", "banned_words"]}),
        ("Защита на входа", {"fields": ["login_max_attempts", "login_lockout_minutes"]}),
        (None, {"fields": ["updated_at"]}),
    ]
    readonly_fields = ["assistant_status", "updated_at"]
    actions_detail = ["check_assistant"]

    @admin.display(description="състояние на услугата")
    def assistant_status(self, obj):
        """Пита услугата на асистента дали работи и има ли ключ за избрания доставчик."""
        ok, message = check_assistant_health(obj.llm_provider if obj else None)
        color = "#1a7f37" if ok else "#cf222e"
        return format_html('<strong style="color:{}">● {}</strong>', color, message)

    @action(description="Провери асистента", url_path="check-assistant", icon="network_check")
    def check_assistant(self, request, object_id):
        """Праща една кратка заявка към избрания модел и казва дали е отговорил (със запазените настройки)."""
        ok, message = check_model()
        (messages.success if ok else messages.error)(request, message)
        return redirect(reverse("admin:economy_gamesettings_change", args=[object_id]))

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
    list_display = ["name", "kind", "sponsor", "responsible", "price", "min_level", "stock", "only_from_mission", "is_active"]
    list_editable = ["price", "min_level", "is_active"]
    list_filter = ["kind", "sponsor", "only_from_mission", "is_active"]


@admin.register(Sponsor)
class SponsorAdmin(ModelAdmin):
    list_display = ["name", "website"]


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
    list_display = ["created_at", "student", "amount", "reason", "is_bonus", "created_by"]
    list_filter = ["is_bonus", "created_at"]
    actions = ["undo_selected"]

    @admin.action(description="Отмени избраните награди (XP и монетите от тях)")
    def undo_selected(self, request, queryset):
        from economy.services import undo_approval, undo_bonus
        from missions.services import GameRuleError

        done, problems = 0, []
        for entry in queryset.select_related("claim", "claim__mission", "student"):
            try:
                if entry.is_bonus:
                    undo_bonus(request.user, entry, "отменено от администратора")
                elif entry.claim_id:
                    undo_approval(request.user, entry.claim, "отменено от администратора")
                else:
                    raise GameRuleError("не е бонус или мисия")
                done += 1
            except GameRuleError as error:
                problems.append(f"{entry}: {error}")
        self.message_user(request, f"Отменени: {done}." + (" Пропуснати: " + "; ".join(problems) if problems else ""),
                          messages.SUCCESS if not problems else messages.WARNING)
    search_fields = ["student__nickname", "student__email", "reason"]


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ["created_at", "student", "amount", "kind", "reason", "created_by"]
    list_filter = ["kind", "created_at"]
    search_fields = ["student__nickname", "student__email", "reason"]


@admin.register(CoinWeek)
class CoinWeekAdmin(ReadOnlyLedgerAdmin):
    list_display = ["week_start", "student", "carry_in", "xp_earned", "xp_used", "coins_earned"]
    list_filter = ["week_start"]
    search_fields = ["student__nickname", "student__email"]


@admin.register(Purchase)
class PurchaseAdmin(ReadOnlyLedgerAdmin):
    list_display = ["purchased_at", "student", "privilege", "price_paid", "claim", "used_at", "marked_used_by"]
    list_filter = ["privilege", "used_at"]
    search_fields = ["student__nickname", "student__email"]
