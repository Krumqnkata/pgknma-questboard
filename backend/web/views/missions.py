"""
Страниците за ученици и учители (Django шаблони).

Тук няма правила на играта – те са в missions/services.py.
Изгледите само проверяват ролята, показват данни и викат услугите.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Guild, User
from accounts.permissions import role_required
from missions.models import Claim, Mission
from missions.services import GameRuleError, missions_for_student, missions_for_teacher, submit_claim

from .forms import ClaimForm, MissionForm

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


@login_required
def home(request):
    """Всеки отива на своята начална страница според ролята."""
    if request.user.is_admin_role:
        return redirect("admin:index")
    return redirect("mission_list")


@login_required
def profile(request):
    return render(request, "web/profile.html")


# ---------- Мисии ----------

@role_required(STUDENT, TEACHER)
def mission_list(request):
    if request.user.is_teacher:
        return teacher_mission_list(request)
    return student_mission_list(request)


def student_mission_list(request):
    missions = missions_for_student()

    # Филтър по гилдия: ?guild=<id>
    selected_guild = request.GET.get("guild", "")
    if selected_guild.isdigit():
        missions = missions.filter(guild_id=selected_guild)

    # Състоянието на собствените заявки, за да се показва до всяка мисия
    my_claims = {c.mission_id: c for c in Claim.objects.filter(student=request.user)}
    rows = [(mission, my_claims.get(mission.id)) for mission in missions]

    return render(request, "web/student_missions.html", {
        "rows": rows,
        "guilds": Guild.objects.all(),
        "selected_guild": selected_guild,
    })


def teacher_mission_list(request):
    missions = missions_for_teacher(request.user).annotate(
        pending_count=Count("claims", filter=Q(claims__status=Claim.Status.PENDING)),
        claims_count=Count("claims"),
    ).order_by("-is_active", "deadline")
    return render(request, "web/teacher_missions.html", {"missions": missions})


@role_required(TEACHER)
def mission_create(request):
    form = MissionForm(request.POST or None)
    form.instance.created_by = request.user
    if request.method == "POST" and form.is_valid():
        mission = form.save()
        messages.success(request, f"Мисията „{mission.title}“ е публикувана.")
        return redirect("mission_detail", pk=mission.pk)
    return render(request, "web/mission_form.html", {"form": form, "is_new": True})


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
        mission = get_object_or_404(Mission.objects.select_related("guild"), pk=pk, created_by=request.user)
        claims = mission.claims.select_related("student", "student__school_class").order_by("status", "-submitted_at")
        return render(request, "web/mission_detail.html", {"mission": mission, "claims": claims})

    # Ученик: вижда активните мисии и тези, за които вече има заявка.
    mission = get_object_or_404(
        Mission.objects.select_related("guild").filter(Q(is_active=True) | Q(claims__student=request.user)).distinct(),
        pk=pk,
    )
    my_claim = Claim.objects.filter(mission=mission, student=request.user).first()
    can_claim = mission.is_open() and (my_claim is None or my_claim.status == Claim.Status.REJECTED)
    form = ClaimForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            submit_claim(request.user, mission, form.cleaned_data["evidence"])
        except GameRuleError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Заявката е изпратена. Учителят ще я провери.")
        return redirect("mission_detail", pk=mission.pk)

    return render(request, "web/mission_detail.html", {
        "mission": mission, "my_claim": my_claim, "can_claim": can_claim, "form": form,
    })
