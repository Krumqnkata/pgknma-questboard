"""Страницата „Награди“: учителят дава бонус XP или значка на ученик без мисия."""
from django.contrib import messages
from django.shortcuts import redirect, render

from accounts.models import User
from accounts.permissions import role_required
from badges.models import StudentBadge
from badges.services import give_badge, take_badge
from economy.models import GameSettings, XPTransaction
from economy.services import bonus_left_this_week, can_undo, give_bonus, undo_bonus
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

    if action in ("undo_bonus", "undo_badge"):
        return _undo(request, action)

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
        "recent_bonuses": [
            (entry, can_undo(teacher, entry.created_by_id, entry.created_at) and not hasattr(entry, "reversal"))
            for entry in XPTransaction.objects.filter(created_by=teacher, is_bonus=True, amount__gt=0)
                                              .select_related("student", "reversal")[:10]
        ],
        "recent_badges": [
            (award, can_undo(teacher, award.given_by_id, award.awarded_at))
            for award in StudentBadge.objects.filter(given_by=teacher).select_related("student", "badge")[:10]
        ],
        "undo_days": GameSettings.load().undo_days,
    })


def _undo(request, action):
    """Отмяна на бонус или отнемане на значка – с причина, която ученикът вижда."""
    why = request.POST.get("why", "")
    pk = request.POST.get("id", "")
    try:
        if action == "undo_bonus":
            entry = XPTransaction.objects.select_related("student").filter(pk=pk if pk.isdigit() else 0).first()
            if not entry:
                raise GameRuleError("Няма такъв бонус.")
            undo_bonus(request.user, entry, why)
            messages.success(request, f"Бонусът на {entry.student.nickname} е отменен.")
        else:
            award = StudentBadge.objects.select_related("student", "badge").filter(pk=pk if pk.isdigit() else 0).first()
            if not award:
                raise GameRuleError("Няма такава значка.")
            take_badge(request.user, award, why)
            messages.success(request, f"Значката „{award.badge.name}“ е отнета от {award.student.nickname}.")
    except GameRuleError as error:
        messages.error(request, str(error))
    return redirect("rewards")
