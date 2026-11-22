"""
Страници за мисиите: списък, детайли, създаване, редакция и заявка за изпълнение.

Тук няма правила на играта – те са в missions/services.py.
Изгледите само проверяват ролята, показват данни и викат услугите.
"""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Guild, User
from accounts.permissions import role_required
from assistant_bridge.models import Hint
from assistant_bridge.services import AssistantError, draft_mission, unused_hint_tokens
from economy.models import GameSettings
from missions.models import Claim, Mission
from missions.services import GameRuleError, missions_for_student, missions_for_teacher, submit_claim

from ..forms import ClaimForm, MissionForm, ReviewForm

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


@role_required(STUDENT, TEACHER)
def mission_list(request):
    if request.user.is_teacher:
        return _teacher_mission_list(request)
    return _student_mission_list(request)


def _student_mission_list(request):
    # Колко ученици са изпълнили всяка мисия – показва се на картата.
    missions = missions_for_student().annotate(
        done_count=Count("claims", filter=Q(claims__status=Claim.Status.APPROVED)),
    )

    # Филтър по гилдия: ?guild=<id>
    selected_guild = request.GET.get("guild", "")
    if selected_guild.isdigit():
        missions = missions.filter(guild_id=selected_guild)

    # Състоянието на собствените заявки, за да се показва до всяка мисия
    my_claims = {c.mission_id: c for c in Claim.objects.filter(student=request.user)}
    rows = [(mission, my_claims.get(mission.id)) for mission in missions]

    now = timezone.now()
    return render(request, "web/student_missions.html", {
        "rows": rows,
        "guilds": Guild.objects.all(),
        "selected_guild": selected_guild,
        "max_xp": GameSettings.load().max_xp_per_mission,
        "new_since": now - timedelta(days=3),   # „нова“ – създадена през последните 3 дни
        "soon": now + timedelta(days=3),        # „остават N дни“ – срокът е до 3 дни
    })


def _teacher_mission_list(request):
    missions = missions_for_teacher(request.user).annotate(
        pending_count=Count("claims", filter=Q(claims__status=Claim.Status.PENDING)),
        claims_count=Count("claims"),
    ).order_by("-is_active", "deadline")
    return render(request, "web/teacher_missions.html", {"missions": missions})


@role_required(TEACHER)
def mission_create(request):
    # Бутонът „Чернова с асистента“ попълва формата, но нищо не се публикува (Ф11).
    if request.method == "POST" and "draft_idea" in request.POST:
        return _mission_draft(request)

    form = MissionForm(request.POST or None)
    form.instance.created_by = request.user
    if request.method == "POST" and form.is_valid():
        mission = form.save()
        messages.success(request, f"Мисията „{mission.title}“ е публикувана.")
        return redirect("mission_detail", pk=mission.pk)
    return render(request, "web/mission_form.html", {"form": form, "is_new": True})


def _mission_draft(request):
    idea = request.POST.get("draft_idea", "")
    initial = {}
    try:
        initial = draft_mission(request.user, idea)
    except (GameRuleError, AssistantError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Черновата е готова. Прегледайте и редактирайте, преди да публикувате.")
    form = MissionForm(initial=initial)
    return render(request, "web/mission_form.html", {"form": form, "is_new": True, "draft_idea": idea})


@role_required(TEACHER)
def mission_edit(request, pk):
    # Само авторът редактира мисията си. За чужда мисия – страница 404.
    mission = get_object_or_404(Mission, pk=pk, created_by=request.user)
    form = MissionForm(request.POST or None, instance=mission)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Промените са запазени.")
        return redirect("mission_detail", pk=mission.pk)
    return render(request, "web/mission_form.html", {"form": form, "is_new": False, "mission": mission})


@role_required(STUDENT, TEACHER)
def mission_detail(request, pk):
    if request.user.is_teacher:
        return _teacher_mission_detail(request, pk)
    return _student_mission_detail(request, pk)


def _teacher_mission_detail(request, pk):
    mission = get_object_or_404(Mission.objects.select_related("guild"), pk=pk, created_by=request.user)
    claims = mission.claims.select_related("student", "student__school_class").prefetch_related(
        "files").order_by("status", "-submitted_at")
    return render(request, "web/mission_detail.html", {
        "mission": mission, "claims": claims, "review_form": ReviewForm(),
    })


def _student_mission_detail(request, pk):
    # Ученикът вижда активните мисии и тези, за които вече има заявка.
    mission = get_object_or_404(
        Mission.objects.select_related("guild").filter(Q(is_active=True) | Q(claims__student=request.user)).distinct(),
        pk=pk,
    )
    my_claim = Claim.objects.filter(mission=mission, student=request.user).first()
    can_claim = mission.is_open() and (my_claim is None or my_claim.status == Claim.Status.REJECTED)
    form = ClaimForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        try:
            submit_claim(request.user, mission, form.cleaned_data["evidence"], form.cleaned_data.get("files", []))
        except GameRuleError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Заявката е изпратена. Учителят ще я провери.")
        return redirect("mission_detail", pk=mission.pk)

    return render(request, "web/mission_detail.html", {
        "mission": mission, "my_claim": my_claim, "can_claim": can_claim, "form": form,
        "hints": Hint.objects.filter(student=request.user, mission=mission),
        "hint_tokens": unused_hint_tokens(request.user).count(),
    })
