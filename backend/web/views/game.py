"""
Страници за играта: начало, проверка на заявки, магазин, привилегии и класация.
Правилата са в economy/services.py – тук само се показва и се викат услугите.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Guild, SchoolClass, User
from accounts.nicknames import change_nickname, next_change_at
from accounts.permissions import role_required
from badges.services import award_badges, badge_cards
from economy.awards import recent_awards
from economy import leaderboard
from economy.models import GameSettings, Privilege, Purchase, XPTransaction
from economy.services import owned_cosmetics, undo_approval, wear
from economy.services import (
    SELF_USED,
    active_privileges, approve_claim, buy_privilege, is_unlocked, mark_purchase_used, pending_claims_for,
    reject_claim, student_stats, unused_purchases,
)
from economy.words import coins_text
from missions.deadlines import apply_extensions
from missions.models import Claim, Mission
from missions.services import GameRuleError, missions_for_student
from notifications.models import Notification

from ..cycle import first_steps, student_cycle, teacher_cycle
from ..forms import NicknameForm, ReviewForm

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


def home(request):
    """Всеки отива на своята начална страница според ролята. Без вход – представяне на платформата."""
    if not request.user.is_authenticated:
        return landing(request)
    if request.user.is_admin_role:
        return redirect("admin:index")
    if request.user.is_teacher:
        return redirect("review_list")
    return student_home(request)


def landing(request):
    """Публична страница: какво е Questboard. Показва само общи числа, без лични данни."""
    mission = missions_for_student().order_by("-created_at").first()
    mission_fields = [
        ("title", mission.title), ("guild", mission.guild.name), ("xp", mission.xp),
        ("deadline", timezone.localtime(mission.deadline).strftime("%d.%m.%Y")),
    ] if mission else [("title", "Първата мисия"), ("guild", "Техничари"), ("xp", 50)]

    return render(request, "web/landing.html", {
        "mission_fields": mission_fields,
        "guilds": Guild.objects.all(),
        "numbers": {
            "missions": missions_for_student().count(),
            "students": User.objects.filter(role=STUDENT, is_active=True).count(),
            "approved": Claim.objects.filter(status=Claim.Status.APPROVED).count(),
            "xp": XPTransaction.objects.aggregate(total=Sum("amount"))["total"] or 0,
        },
    })


def student_home(request):
    student = request.user
    stats = student_stats(student)
    award_badges(student)  # ако администраторът е добавил нова значка, която ученикът вече е заслужил
    cards = badge_cards(student)
    # Ново ниво и нови значки се показват веднъж с голяма карта, после са прочетени.
    celebrations = list(student.notifications.filter(
        read_at__isnull=True,
        kind__in=[Notification.Kind.LEVEL_UP, Notification.Kind.BADGE, Notification.Kind.BONUS, Notification.Kind.REWARD]).order_by("created_at"))
    if celebrations:
        student.notifications.filter(pk__in=[n.pk for n in celebrations]).update(read_at=timezone.now())
    now = timezone.now()
    suggested = apply_extensions(student, suggested_missions(student))
    return render(request, "web/student_home.html", {
        "stats": stats,
        "suggested": suggested,
        "cycle": student_cycle(student, stats, suggested),
        "first_steps": first_steps(student, stats),
        "max_xp": GameSettings.load().max_xp_per_mission,
        "new_since": now - timedelta(days=3),
        "soon": now + timedelta(days=3),
        "recent_claims": Claim.objects.filter(student=student).select_related("mission")
                                      .order_by("-reviewed_at", "-submitted_at")[:5],
        "recent_xp": student.xp_transactions.order_by("-created_at")[:5],
        "recent_coins": student.coin_transactions.order_by("-created_at")[:5],
        "badge_cards": cards,
        "badges_earned": sum(card.earned for card in cards),
        "celebrations": celebrations,
        "recent_awards": recent_awards(6),
    })


def suggested_missions(student, limit=4):
    """
    „Мисии за теб“ на началната страница (до 4, за да се подредят 2×2 до картата
    на играча): активни мисии без заявка от ученика,
    първо тези на неговите гилдии, после по най-близък срок.
    """
    return (missions_for_student(student)
            .exclude(claims__student=student)
            .annotate(
                # Първо домашните за класа и мисиите на собствената гилдия.
                own_guild=Case(When(kind=Mission.Kind.HOMEWORK, then=Value(0)),
                               When(guild_id__in=student.guild_ids, then=Value(0)), default=Value(1),
                               output_field=IntegerField()),
                done_count=Count("claims", filter=Q(claims__status=Claim.Status.APPROVED)),
            )
            .order_by("own_guild", "deadline")[:limit])


@login_required
def profile(request):
    user = request.user
    context = {}
    if user.is_student:
        action = request.POST.get("action", "nickname")
        if request.method == "POST" and action != "nickname":
            return _profile_look(request, action)
        form = NicknameForm(request.POST or None, initial={"nickname": user.nickname})
        if request.method == "POST" and form.is_valid():
            try:
                nickname = change_nickname(user, form.cleaned_data["nickname"])
            except ValidationError as error:
                form.add_error("nickname", error)
            else:
                messages.success(request, f"Псевдонимът ти вече е „{nickname}“.")
                return redirect("profile")
        context = {
            "earned_badges": [card for card in badge_cards(user) if card.earned],
            "nickname_form": form,
            "next_nickname_change": next_change_at(user),
            "nickname_change_days": GameSettings.load().nickname_change_days,
            "titles": [item for item in owned_cosmetics(user) if item.kind == Privilege.Kind.TITLE],
            "frames": [item for item in owned_cosmetics(user) if item.kind == Privilege.Kind.FRAME],
        }
    elif user.is_teacher:
        context = {"led_guilds": user.led_guilds.all()}
    return render(request, "web/profile.html", context)


def _profile_look(request, action):
    """Външният вид в класациите: нова шарка на аватара, титла и рамка."""
    user = request.user
    if action == "avatar":
        user.avatar_seed += 1
        user.save(update_fields=["avatar_seed"])
        messages.success(request, "Аватарът ти има нова шарка.")
    elif action in ("title", "frame"):
        chosen = request.POST.get(action, "")
        item = Privilege.objects.filter(pk=chosen).first() if chosen.isdigit() else None
        kind = Privilege.Kind.TITLE if action == "title" else Privilege.Kind.FRAME
        try:
            wear(user, item, kind=kind)
        except GameRuleError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Запазено.")
    return redirect("profile")


# ---------- Проверка на заявки (учител) ----------

@role_required(TEACHER)
def review_list(request):
    claims = list(pending_claims_for(request.user).order_by("submitted_at"))
    return render(request, "web/review_list.html", {"claims": claims, "cycle": teacher_cycle(request.user, len(claims))})


@require_POST
@role_required(TEACHER)
def review_bulk(request):
    """Потвърждава избраните заявки наведнъж. Всяка минава през същата проверка на правата."""
    picked = [pk for pk in request.POST.getlist("claim") if pk.isdigit()]
    done, xp, problems = 0, 0, []
    for claim in Claim.objects.filter(pk__in=picked).select_related("mission", "student").order_by("submitted_at"):
        try:
            result = approve_claim(claim, request.user)
        except GameRuleError as error:
            problems.append(f"{claim.student.nickname}: {error}")
        else:
            done += 1
            xp += result.xp * (1 + result.team)
    if done:
        messages.success(request, f"Потвърдени: {done}. Учениците получават общо {xp} XP.")
    elif not problems:
        messages.error(request, "Не сте избрали заявка.")
    for problem in problems:
        messages.error(request, problem)
    return redirect("review_list")


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
            team = f" Същото получават и съотборниците ({result.team})." if result.team else ""
            messages.success(request, f"Потвърдено: {nickname} получава {result.xp} XP{coins}.{team}")
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
    items = list(active_privileges())
    stats = student_stats(request.user)
    for item in items:
        item.unlocked = is_unlocked(item, stats.level)
    owned = {item.pk for item in owned_cosmetics(request.user)}
    return render(request, "web/shop.html", {
        "privileges": [item for item in items if item.kind == Privilege.Kind.PRIVILEGE],
        "sponsor_rewards": [item for item in items if item.kind == Privilege.Kind.SPONSOR],
        # Първо отключените; сред тях и сред заключените – по ниво и цена.
        "cosmetics": sorted((item for item in items if item.is_cosmetic),
                            key=lambda item: (not item.unlocked, item.min_level, item.price)),
        "owned": owned,
        "stats": stats,
        "purchases": Purchase.objects.filter(student=request.user).select_related("privilege__responsible"),
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
        if privilege.is_cosmetic:
            messages.success(request, f"Купено: {privilege.name}. Вече се вижда в класацията – смени го от профила.")
        elif privilege.kind == Privilege.Kind.SPONSOR:
            messages.success(request, f"Купено: {privilege.name}. Виж в „Моите покупки“ от кого ще го получиш.")
        elif privilege.code in SELF_USED:
            messages.success(request, f"Купено: {privilege.name}. Използва се от страницата на мисията или домашната.")
        else:
            messages.success(request, f"Купено: {privilege.name}. Покажи го на учителя, когато го използваш.")
    return redirect("shop")


# ---------- Купени привилегии (учител) ----------

@role_required(TEACHER)
def purchase_list(request):
    return render(request, "web/purchases.html", {"purchases": unused_purchases(request.user)})


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
    period = "week" if request.GET.get("period") == "week" else "all"
    tables = leaderboard.rankings(
        period,
        guild_id=int(guild_id) if guild_id.isdigit() else None,
        class_id=int(class_id) if class_id.isdigit() else None,
        limit=None,  # всички – за да намерим и мястото на ученика, ако не е в показаните
    )
    everyone = tables["students"]
    top = 100 if request.GET.get("top") == "100" else 10
    shown = everyone[:top]
    me = None
    if request.user.is_student and not any(row.user.pk == request.user.pk for row in shown):
        me = next((row for row in everyone if row.user.pk == request.user.pk), None)
    return render(request, "web/leaderboard.html", {
        "guild_rows": tables["guilds"],
        "class_rows": tables["classes"],
        "student_rows": shown,
        "podium": [row for row in shown[:3] if row.xp],
        "top": top,
        "total_students": len(everyone),
        "my_row": me,
        "period": period,
        "guilds": Guild.objects.all(),
        "classes": SchoolClass.objects.all(),
        "selected_guild": guild_id,
        "selected_class": class_id,
    })



@require_POST
@role_required(TEACHER, User.Role.ADMIN)
def claim_undo(request, pk):
    """Учителят отменя потвърждение, дадено по грешка: XP и монетите се връщат, заявката става отказана."""
    claim = get_object_or_404(Claim.objects.select_related("mission", "student"), pk=pk)
    try:
        undo_approval(request.user, claim, request.POST.get("why", ""))
    except GameRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Потвърждението за {claim.student.nickname} е отменено.")
    return redirect("mission_detail", pk=claim.mission_id)
