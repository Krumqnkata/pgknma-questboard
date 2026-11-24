"""Страницата „Проверка на системата“ в администрацията (правилата са в diagnostics.py)."""
from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from assistant_bridge.services import AssistantError, explain_problems
from economy.models import GameSettings
from missions.errors import GameRuleError

from .diagnostics import FIXES, find_problems


@require_http_methods(["GET", "POST"])
def system_check(request):
    # admin.site.admin_view пуска само служители; тук се иска и ролята администратор.
    if not request.user.is_admin_role:
        messages.error(request, "Проверката на системата е само за администратори.")
        return redirect("admin:index")

    explanation = None
    problems = find_problems()
    if request.method == "POST":
        code = request.POST.get("fix")
        if code:
            _apply(request, code, problems)
            return redirect("system_check")
        try:
            explanation = explain_problems(request.user, problems)
        except (AssistantError, GameRuleError) as error:
            messages.error(request, str(error))

    return render(request, "admin/system_check.html", {
        **admin.site.each_context(request),
        "title": "Проверка на системата",
        "problems": problems,
        "explanation": explanation,
        "assistant_enabled": GameSettings.load().assistant_enabled,
    })


def _apply(request, code, problems):
    problem = next((item for item in problems if item.code == code and item.fix_label), None)
    if problem is None or code not in FIXES:
        messages.error(request, "Този проблем вече го няма или се поправя само ръчно.")
        return
    with transaction.atomic():
        count = FIXES[code]()
        LogEntry.objects.create(
            user_id=request.user.pk, content_type=ContentType.objects.get_for_model(User),
            object_id=str(request.user.pk), object_repr="Проверка на системата"[:200], action_flag=CHANGE,
            change_message=f"{problem.title}: {problem.fix_label} ({count})",
        )
    messages.success(request, f"{problem.title}: поправени {count}.")
