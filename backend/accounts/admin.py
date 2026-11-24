import base64
import csv
import io

from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .importer import COLUMNS, import_users
from .models import Guild, LoginAttempt, NicknameChange, SchoolClass, User

# Ролите са в полето User.role, затова групите на Django не ни трябват.
admin.site.unregister(Group)


class NicknameChangeInline(TabularInline):
    """Историята на псевдонима на ученика – само за четене."""

    model = NicknameChange
    fk_name = "student"
    fields = ["old", "new", "changed_by", "changed_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    verbose_name_plural = "история на псевдонима"

    def has_add_permission(self, request, obj=None):
        return False


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
        ("Роля", {"fields": ["role", "is_active", "must_change_password"]}),
        ("Само за ученици", {"fields": ["nickname", "school_class", "guild"]}),
        ("Дати", {"fields": ["last_login", "date_joined"]}),
    ]
    # Формата за нов потребител има всички полета наведнъж – иначе ученик не може
    # да се създаде, защото псевдонимът, класът и гилдията са задължителни за него.
    add_fieldsets = [
        ("Вход", {
            "classes": ["wide"],
            "fields": ["email", "password1", "password2", "must_change_password"],
        }),
        ("Лични данни", {"classes": ["wide"], "fields": ["first_name", "last_name"]}),
        ("Роля", {"classes": ["wide"], "fields": ["role"]}),
        ("Само за ученици", {
            "classes": ["wide"],
            "description": "Задължителни, когато ролята е „Ученик“. За учител и администратор се оставят празни.",
            "fields": ["nickname", "school_class", "guild"],
        }),
    ]
    readonly_fields = ["last_login", "date_joined"]
    actions_list = ["import_csv"]  # бутон над списъка с потребители

    def get_inlines(self, request, obj):
        return [NicknameChangeInline] if obj and obj.is_student else []

    def save_model(self, request, obj, form, change):
        """Смяната на псевдоним от администратора също влиза в историята."""
        old = User.objects.get(pk=obj.pk).nickname if change else None
        super().save_model(request, obj, form, change)
        if change and "nickname" in form.changed_data and obj.nickname:
            NicknameChange.objects.create(student=obj, old=old or "", new=obj.nickname, changed_by=request.user)

    @action(description="Внеси от CSV", url_path="import-csv", icon="upload_file")
    def import_csv(self, request):
        """Внася ученици и учители от CSV и показва временните им пароли – само веднъж."""
        return _import_page(self, request)


def _import_page(model_admin, request):
    context = {
        **model_admin.admin_site.each_context(request),
        "title": "Внасяне на потребители",
        "columns": ",".join(COLUMNS),
        "opts": model_admin.model._meta,
    }
    if request.method == "POST" and request.FILES.get("file"):
        try:
            text = request.FILES["file"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "Файлът трябва да е записан в UTF-8 (в Excel: „CSV UTF-8“).")
        else:
            result = import_users(text)
            if result.ok:
                context.update(result=result, download=_passwords_csv(result.created))
                response = render(request, "admin/accounts/import_result.html", context)
                add_never_cache_headers(response)  # страницата с паролите не се пази в кеша на браузъра
                return response
            for error in result.errors[:20]:
                messages.error(request, error)
            if len(result.errors) > 20:
                messages.error(request, f"… и още {len(result.errors) - 20} грешки.")
    return render(request, "admin/accounts/import.html", context)


def _passwords_csv(created):
    """CSV с временните пароли като data: адрес – свалят се от браузъра, без да се пазят на сървъра."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["имейл", "име", "роля", "псевдоним", "клас", "временна парола"])
    for user in created:
        writer.writerow([user.email, user.name, user.role, user.nickname, user.school_class, user.password])
    data = base64.b64encode(("﻿" + buffer.getvalue()).encode("utf-8")).decode("ascii")
    return f"data:text/csv;charset=utf-8;base64,{data}"


@admin.register(Guild)
class GuildAdmin(ModelAdmin):
    list_display = ["name", "code", "description"]


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


@admin.register(LoginAttempt)
class LoginAttemptAdmin(ModelAdmin):
    """Неуспешните входове. Изтриването на записите за един имейл го отключва веднага."""

    list_display = ["email", "ip_address", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["email", "ip_address"]
    actions = ["unlock"]

    @admin.action(description="Отключи входа за избраните имейли и адреси")
    def unlock(self, request, queryset):
        emails = set(queryset.values_list("email", flat=True))
        addresses = set(queryset.exclude(ip_address=None).values_list("ip_address", flat=True))
        deleted, _ = LoginAttempt.objects.filter(email__in=emails).delete()
        deleted += LoginAttempt.objects.filter(ip_address__in=addresses).delete()[0]
        self.message_user(request, f"Входът е отключен. Изтрити записи: {deleted}.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
