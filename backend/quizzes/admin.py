from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Attempt, GuildTest, Question, TestSession


class QuestionInline(TabularInline):
    model = Question
    fields = ["kind", "text", "answers", "seconds", "is_approved"]
    extra = 0


@admin.register(GuildTest)
class GuildTestAdmin(ModelAdmin):
    list_display = ["title", "guild", "kind", "questions_count", "seconds", "pass_percent", "xp", "is_active", "created_by"]
    list_filter = ["guild", "kind", "is_active"]
    inlines = [QuestionInline]


class ReadOnlyAdmin(ModelAdmin):
    """Опитите и сесиите се правят само от самите тестове."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TestSession)
class TestSessionAdmin(ReadOnlyAdmin):
    list_display = ["opened_at", "test", "teacher", "expires_at"]
    list_filter = ["test__guild"]


@admin.register(Attempt)
class AttemptAdmin(ReadOnlyAdmin):
    list_display = ["started_at", "student", "test", "status", "correct", "left_page", "finished_at"]
    list_filter = ["status", "test__guild", "test__kind"]
    search_fields = ["student__nickname", "student__email"]
    exclude = ["secret"]
