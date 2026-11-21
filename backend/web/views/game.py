"""
Страници за играта: начало, проверка на заявки, магазин, привилегии и класация.
Правилата са в economy/services.py – тук само се показва и се викат услугите.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Guild, SchoolClass, User
from accounts.permissions import role_required
from economy import leaderboard
from economy.models import Privilege, Purchase
from economy.services import (
    active_privileges, approve_claim, buy_privilege, mark_purchase_used, pending_claims_for,
    reject_claim, student_stats, unused_purchases,
)
from economy.words import coins_text
from missions.models import Claim
from missions.services import GameRuleError

from ..forms import ReviewForm

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


@login_required
def home(request):
    """Всеки отива на своята начална страница според ролята."""
    if request.user.is_admin_role:
        return redirect("admin:index")
    if request.user.is_teacher:
        return redirect("review_list")
    return student_home(request)


def student_home(request):
    student = request.user
    return render(request, "web/student_home.html", {
        "stats": student_stats(student),
        "recent_claims": Claim.objects.filter(student=student).select_related("mission")
                                      .order_by("-reviewed_at", "-submitted_at")[:5],
        "recent_xp": student.xp_transactions.order_by("-created_at")[:5],
        "recent_coins": student.coin_transactions.order_by("-created_at")[:5],
    })


@login_required
def profile(request):
    return render(request, "web/profile.html")


# ---------- Проверка на заявки (учител) ----------

@role_required(TEACHER)
def review_list(request):
    return render(request, "web/review_list.html", {
        "claims": pending_claims_for(request.user).order_by("submitted_at"),
        "review_form": ReviewForm(),
    })


@require_POST
@role_required(TEACHER)
def review_claim(request, pk):
    """Потвърждава или отказва заявка. Връща учителя там, откъдето е дошъл."""
    claim = get_object_or_404(Claim.objects.select_related("mission", "student"), pk=pk)
    form = ReviewForm(request.POST)
    back = _safe_next(request)
    if not form.is_valid():
        messages.error(request, "Невалидна заявка.")
        return redirect(back)

    comment = form.cleaned_data["comment"]
    nickname = claim.student.nickname
    try:
        if form.cleaned_data["decision"] == ReviewForm.APPROVE:
            result = approve_claim(claim, request.user, comment)
            coins = f" и {coins_text(result.coins)}" if result.coins else " (без монети – седмичният лимит е достигнат)"
            messages.success(request, f"Потвърдено: {nickname} получава {result.xp} XP{coins}.")
            if result.new_level:
                messages.success(request, f"{nickname} достигна {result.new_level}!")
        else:
            reject_claim(claim, request.user, comment)
            messages.success(request, f"Заявката на {nickname} е отказана. Ученикът може да я подаде отново.")
    except GameRuleError as error:
        messages.error(request, str(error))
    return redirect(back)


def _safe_next(request):
    """
    Адресът, към който да се върнем след действие.
    Приемаме само адрес от нашия сайт – защита от пренасочване към чужд сайт.
    """
    url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return reverse("review_list")


# ---------- Магазин (ученик) ----------

@role_required(STUDENT)
def shop(request):
    return render(request, "web/shop.html", {
        "privileges": active_privileges(),
        "stats": student_stats(request.user),
        "purchases": Purchase.objects.filter(student=request.user).select_related("privilege"),
    })


@require_POST
@role_required(STUDENT)
def shop_buy(request, pk):
    privilege = get_object_or_404(Privilege, pk=pk)
    try:
        buy_privilege(request.user, privilege)
    except GameRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Купено: {privilege.name}. Покажи го на учителя, когато го използваш.")
    return redirect("shop")


# ---------- Купени привилегии (учител) ----------

@role_required(TEACHER)
def purchase_list(request):
    return render(request, "web/purchases.html", {"purchases": unused_purchases()})


@require_POST
@role_required(TEACHER)
def purchase_use(request, pk):
    purchase = get_object_or_404(Purchase.objects.select_related("student", "privilege"), pk=pk)
    try:
        mark_purchase_used(purchase, request.user)
    except GameRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{purchase.privilege.name} на {purchase.student.nickname} е отбелязан като използван.")
    return redirect("purchase_list")


# ---------- Класация ----------

@role_required(STUDENT, TEACHER)
def leaderboard_view(request):
    guild_id = request.GET.get("guild", "")
    class_id = request.GET.get("class", "")
    return render(request, "web/leaderboard.html", {
        "guild_rows": leaderboard.guild_ranking(),
        "class_rows": leaderboard.class_ranking(),
        "student_rows": leaderboard.student_ranking(
            guild_id=int(guild_id) if guild_id.isdigit() else None,
            class_id=int(class_id) if class_id.isdigit() else None,
        ),
        "guilds": Guild.objects.all(),
        "classes": SchoolClass.objects.all(),
        "selected_guild": guild_id,
        "selected_class": class_id,
    })
