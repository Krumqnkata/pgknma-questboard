from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Guild, SchoolClass, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Управление на потребителите. Пренаписано, защото входът е с имейл."""

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
class GuildAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
