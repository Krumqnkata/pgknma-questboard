"""Страниците за гилдиите и тестовете им. Правилата са в quizzes/services.py."""
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.guilds import MAIN_CHANGE_DAYS, leave_guild, make_main, next_main_change
from accounts.models import Guild, User
from accounts.permissions import role_required
from assistant_bridge.services import AssistantError, draft_questions
from missions.errors import GameRuleError
from quizzes.models import Attempt, GuildTest, Question, TestSession
from quizzes.services import (
    answer_question, close_session, current_question, finish_expired, note_left_page, open_session, save_drafts,
    start_attempt, tests_for, void_attempt,
)

from ..forms import GuildTestForm, QuestionDraftForm, QuestionForm, SessionForm

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


# ---------- Ученик ----------

@role_required(STUDENT, TEACHER)
def guild_list(request):
    if request.user.is_teacher:
        return _guilds_for_teacher(request)
    tests = {}
    for test, problem in tests_for(request.user):
        tests.setdefault(test.guild_id, []).append((test, problem))
    guilds = _guilds_with_members()
    return render(request, "web/guilds.html", {
        "guild_rows": [(guild, tests.get(guild.pk, [])) for guild in
                       sorted(guilds, key=lambda g: (g.pk != request.user.guild_id, g.pk != request.user.second_guild_id, g.name))],
        "attempts": Attempt.objects.filter(student=request.user).select_related("test", "test__guild")[:8],
        "running": Attempt.objects.filter(student=request.user, status=Attempt.Status.RUNNING).first(),
        "next_main_change": next_main_change(request.user),
        "main_change_days": MAIN_CHANGE_DAYS,
    })


def _guilds_with_members():
    return Guild.objects.prefetch_related("leaders").annotate(
        member_count=Count("members", filter=Q(members__role=STUDENT, members__is_active=True), distinct=True)
        + Count("second_members", filter=Q(second_members__role=STUDENT, second_members__is_active=True), distinct=True)
    ).order_by("name")


def _guilds_for_teacher(request):
    """Кой за коя гилдия отговаря; за своите учителят вижда членовете, тестовете и последните опити."""
    guilds = list(_guilds_with_members())
    mine = []
    for guild in guilds:
        if request.user in guild.active_leaders:
            mine.append({
                "guild": guild,
                "members": User.objects.filter(Q(guild=guild) | Q(second_guild=guild), role=STUDENT, is_active=True)
                               .select_related("school_class").order_by("school_class__name", "first_name", "last_name"),
                "tests": guild.tests.filter(is_active=True).select_related("created_by"),
                "attempts": Attempt.objects.filter(test__guild=guild).exclude(status=Attempt.Status.RUNNING)
                                   .select_related("student__school_class", "test")[:8],
            })
    return render(request, "web/guilds_teacher.html", {"guilds": guilds, "mine": mine})


@require_POST
@role_required(STUDENT)
def guild_main(request, pk):
    guild = get_object_or_404(Guild, pk=pk)
    try:
        make_main(request.user, guild)
    except GameRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Основната ти гилдия вече е „{guild}“.")
    return redirect("guild_list")


@require_POST
@role_required(STUDENT)
def guild_leave(request, pk):
    guild = get_object_or_404(Guild, pk=pk)
    try:
        leave_guild(request.user, guild)
    except GameRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Напусна гилдия „{guild}“.")
    return redirect("guild_list")


@require_POST
@role_required(STUDENT)
def test_start(request):
    try:
        attempt = start_attempt(request.user, request.POST.get("code"))
    except GameRuleError as error:
        messages.error(request, str(error))
        return redirect("guild_list")
    return redirect("test_attempt", pk=attempt.pk)


@never_cache  # „Назад“ не показва стар въпрос
@role_required(STUDENT)
def test_attempt(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related("test", "test__guild"), pk=pk, student=request.user)
    if request.method == "POST":
        answer_question(attempt, request.POST.get("question"), request.POST.get("answer", ""))
        return redirect("test_attempt", pk=pk)
    shown = current_question(attempt)
    attempt.refresh_from_db()
    if shown is None:
        return render(request, "web/test_result.html", {"attempt": attempt})
    question, left = shown
    return render(request, "web/test_question.html", {
        "attempt": attempt, "question": question, "seconds_left": f"{left:.1f}", "limit": question.time_limit,
        "number": attempt.position + 1, "options": question.shuffled(attempt.secret),
    })


@require_POST
@role_required(STUDENT)
def test_left(request, pk):
    note_left_page(get_object_or_404(Attempt, pk=pk, student=request.user))
    return HttpResponse(status=204)


# ---------- Учител ----------

@role_required(TEACHER)
def test_list(request):
    tests = GuildTest.objects.select_related("guild", "created_by").annotate(
        ready=Count("questions", filter=Q(questions__is_approved=True), distinct=True),
        drafts=Count("questions", filter=Q(questions__is_approved=False), distinct=True)).order_by("guild__name", "kind", "title")
    return render(request, "web/tests.html", {
        "tests": tests, "session_form": SessionForm(),
        "sessions": TestSession.objects.filter(teacher=request.user).select_related("test", "test__guild").annotate(
            attempts_count=Count("attempts")).order_by("-opened_at", "-pk")[:8],
    })


@role_required(TEACHER)
def test_create(request):
    form = GuildTestForm(request.POST or None, instance=GuildTest(created_by=request.user))
    if request.method == "POST" and form.is_valid():
        test = form.save()
        messages.success(request, "Тестът е създаден. Добавете въпросите.")
        return redirect("test_edit", pk=test.pk)
    return render(request, "web/test_form.html", {"form": form})


@role_required(TEACHER)
def test_edit(request, pk):
    """Въпросите на теста. Редактира само авторът, но всеки учител може да го пусне."""
    test = get_object_or_404(GuildTest.objects.select_related("guild"), pk=pk, created_by=request.user)
    action = request.POST.get("action")
    form = GuildTestForm(request.POST if action == "test" else None, instance=test)
    question_form = QuestionForm(request.POST if action == "question" else None, instance=Question(test=test))
    draft_form = QuestionDraftForm(request.POST if action == "draft" else None)
    if action == "test" and form.is_valid():
        form.save()
        messages.success(request, "Промените са запазени.")
        return redirect("test_edit", pk=pk)
    if action == "question" and question_form.is_valid():
        question_form.save()
        messages.success(request, "Въпросът е добавен.")
        return redirect("test_edit", pk=pk)
    if action == "draft" and draft_form.is_valid():
        try:
            drafts = draft_questions(request.user, test, draft_form.cleaned_data["topic"],
                                     draft_form.cleaned_data["count"])
            saved = save_drafts(test, drafts)
        except (AssistantError, GameRuleError) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Асистентът предложи {saved} въпроса. Прегледайте ги и одобрете верните.")
        return redirect("test_edit", pk=pk)
    if action in ("approve", "delete"):
        _question_action(request, test, action)
        return redirect("test_edit", pk=pk)
    return render(request, "web/test_edit.html", {
        "test": test, "form": form, "question_form": question_form, "draft_form": draft_form,
        "questions": test.questions.order_by("is_approved", "id"),
    })


def _question_action(request, test, action):
    pk = request.POST.get("question", "")
    question = test.questions.filter(pk=pk if pk.isdigit() else 0).first()
    if question is None:
        messages.error(request, "Няма такъв въпрос.")
    elif action == "approve":
        question.is_approved = True
        question.save(update_fields=["is_approved"])
        messages.success(request, "Въпросът е одобрен.")
    else:
        question.delete()
        messages.success(request, "Въпросът е изтрит.")


@require_POST
@role_required(TEACHER)
def session_open(request, pk):
    test = get_object_or_404(GuildTest, pk=pk)
    form = SessionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Изберете за колко минути да е пуснат тестът.")
        return redirect("test_list")
    try:
        session = open_session(request.user, test, form.cleaned_data["minutes"])
    except GameRuleError as error:
        messages.error(request, str(error))
        return redirect("test_list")
    return redirect("test_session", pk=session.pk)


@never_cache
@role_required(TEACHER)
def test_session(request, pk):
    session = get_object_or_404(TestSession.objects.select_related("test", "test__guild"), pk=pk, teacher=request.user)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "close":
                close_session(request.user, session)
                messages.success(request, "Тестът е спрян. Започналите могат да довършат.")
            else:
                number = request.POST.get("attempt", "")
                attempt = get_object_or_404(session.attempts, pk=number if number.isdigit() else 0)
                void_attempt(request.user, attempt, request.POST.get("why", ""))
                messages.success(request, "Опитът е анулиран.")
        except GameRuleError as error:
            messages.error(request, str(error))
        return redirect("test_session", pk=pk)
    finish_expired(session)
    return render(request, "web/test_session.html", {
        "session": session,
        "attempts": session.attempts.select_related("student", "student__school_class").order_by("started_at"),
    })
