"""Страницата „Награди“: учителят дава бонус XP или значка на ученик без мисия."""
from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.models import User
from accounts.permissions import role_required
from badges.models import StudentBadge
from badges.services import give_badge
from economy.models import GameSettings, XPTransaction
from economy.services import bonus_left_this_week, give_bonus
from missions.services import GameRuleError

from ..forms import BadgeGiftForm, BonusForm


@role_required(User.Role.TEACHER, User.Role.ADMIN)
def rewards(request):
    teacher = request.user
    action = request.POST.get("action")
    initial = {"student": request.GET.get("student")}
    bonus_form = BonusForm(request.POST if action == "bonus" else None, initial=initial)
    badge_form = BadgeGiftForm(request.POST if action == "badge" else None, initial=initial)

    if action == "bonus" and bonus_form.is_valid():
        data = bonus_form.cleaned_data
        try:
            give_bonus(teacher, data["student"], data["xp"], data["reason"])
        except GameRuleError as error:
            bonus_form.add_error(None, str(error))
        else:
            messages.success(request, f"{data['student'].nickname} получи +{data['xp']} XP.")
            return redirect("rewards")

    if action == "badge" and badge_form.is_valid():
        data = badge_form.cleaned_data
        try:
            give_badge(teacher, data["student"], data["badge"], data["note"])
        except GameRuleError as error:
            badge_form.add_error(None, str(error))
        else:
            messages.success(request, f"{data['student'].nickname} получи значката „{data['badge'].name}“.")
            return redirect("rewards")

    return render(request, "web/rewards.html", {
        "bonus_form": bonus_form,
        "badge_form": badge_form,
        "bonus_left": bonus_left_this_week(teacher),
        "rules": GameSettings.load(),
        "recent_bonuses": XPTransaction.objects.filter(created_by=teacher, is_bonus=True)
                                               .select_related("student")[:10],
        "recent_badges": StudentBadge.objects.filter(given_by=teacher).select_related("student", "badge")[:10],
    })
