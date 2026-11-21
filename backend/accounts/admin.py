from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Guild, SchoolClass, User

# Ролите са в полето User.role, затова групите на Django не ни трябват.
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    """Управление на потребителите. Пренаписано, защото входът е с имейл."""

    # Формите на Unfold – иначе формите за потребител са в стария вид
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "nickname", "school_class", "guild", "is_active"]
    list_filter = ["role", "school_class", "guild", "is_active"]
    search_fields = ["email", "first_name", "last_name", "nickname"]

    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Лични данни", {"fields": ["first_name", "last_name"]}),
        ("Роля", {"fields": ["role", "is_active"]}),
        ("Само за ученици", {"fields": ["nickname", "school_class", "guild"]}),
        ("Дати", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {
            "classes": ["wide"],
            "fields": ["email", "role", "password1", "password2"],
        }),
    ]
    readonly_fields = ["last_login", "date_joined"]


@admin.register(Guild)
class GuildAdmin(ModelAdmin):
    list_display = ["name", "description"]


@admin.register(SchoolClass)
class SchoolClassAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):
    """Кой какво е променил в администрацията – Django го записва сам."""

    list_display = ["action_time", "user", "content_type", "object_repr", "action_flag", "change_message"]
    list_filter = ["action_flag", "content_type"]
    search_fields = ["object_repr", "change_message", "user__email"]
    date_hierarchy = "action_time"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
