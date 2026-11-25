"""
Правилата на тестовете: кой може да започне, време за въпрос, резултат и награда.

Времето се мери само на сървъра. Браузърът показва таймер, но не решава нищо:
следващият въпрос се праща едва след отговор на текущия, а закъснял отговор е грешен.
"""
import random
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.guilds import can_join, join_guild, remove_guild
from accounts.models import MAX_GUILDS, User
from badges.services import award_badges
from economy.services import _undo_xp, award_xp, level_for_xp, xp_total
from missions.errors import GameRuleError
from notifications.models import Notification
from notifications.services import notify

from .models import Attempt, AttemptAnswer, GuildTest, Question, TestSession

MIN_QUESTIONS = 3
GRACE_SECONDS = 2          # за бавен интернет
CODE_TRIES = 10            # грешни кода от един ученик за 10 минути
SESSION_MINUTES = (5, 90)


# ---------- Сесии (учител) ----------

def open_session(teacher, test, minutes):
    if not (teacher.is_teacher or teacher.is_admin_role):
        raise GameRuleError("Само учител може да пусне тест.")
    if not test.is_active:
        raise GameRuleError("Тестът не е активен.")
    if test.approved_questions().count() < MIN_QUESTIONS:
        raise GameRuleError(f"Тестът трябва да има поне {MIN_QUESTIONS} одобрени въпроса.")
    minutes = max(SESSION_MINUTES[0], min(int(minutes), SESSION_MINUTES[1]))
    now = timezone.now()
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not TestSession.objects.filter(code=code, expires_at__gt=now).exists():
            break
    return TestSession.objects.create(test=test, teacher=teacher, code=code, expires_at=now + timedelta(minutes=minutes))


def close_session(teacher, session):
    if not (teacher.is_admin_role or session.teacher_id == teacher.pk):
        raise GameRuleError("Сесията може да спре само учителят, който я е пуснал.")
    if session.is_open:
        session.expires_at = timezone.now()
        session.save(update_fields=["expires_at"])


# ---------- Кой може да започне ----------

def why_not(student, test, now=None):
    """Защо ученикът не може да реши теста сега; празен текст – може."""
    now = now or timezone.now()
    attempts = Attempt.objects.filter(student=student, test=test).exclude(status=Attempt.Status.VOID)
    if attempts.filter(status=Attempt.Status.RUNNING, deadline__gt=now).exists():
        return "Вече решаваш този тест."
    if test.is_entry:
        if test.guild_id in student.guild_ids:
            return "Вече си в тази гилдия."
        if not can_join(student, test.guild_id):
            return f"Вече си в {MAX_GUILDS} гилдии. За нова първо напусни една."
        last = attempts.order_by("-started_at").first()
        if last and now < last.started_at + timedelta(days=test.retry_days):
            when = timezone.localtime(last.started_at + timedelta(days=test.retry_days))
            return f"Нов опит можеш да направиш след {when:%d.%m.%Y, %H:%M}."
        return ""
    if test.guild_id not in student.guild_ids:
        return "Месечният тест е само за членовете на гилдията."
    month = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if attempts.filter(started_at__gte=month).exists():
        return "Вече си решавал този тест този месец."
    return ""


def _find_session(student, code):
    key = f"quiz-code-{student.pk}"
    if cache.get(key, 0) >= CODE_TRIES:
        raise GameRuleError("Твърде много грешни кодове. Опитай пак след 10 минути.")
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    session = TestSession.objects.select_related("test", "test__guild").filter(
        code=code, expires_at__gt=timezone.now()).first() if code else None
    if session is None:
        cache.set(key, cache.get(key, 0) + 1, 600)
        raise GameRuleError("Няма пуснат тест с този код. Провери го при учителя.")
    return session


def start_attempt(student, code):
    """Ученикът въвежда кода и започва. Въпросите се избират и разбъркват за него."""
    if not student.is_student:
        raise GameRuleError("Само ученици решават тестове.")
    session = _find_session(student, code)
    test = session.test
    with transaction.atomic():
        User.objects.select_for_update().get(pk=student.pk)  # двойно натискане не прави два опита
        running = Attempt.objects.filter(student=student, session=session, status=Attempt.Status.RUNNING).first()
        if running and running.deadline > timezone.now():
            return running
        problem = why_not(student, test)
        if problem:
            raise GameRuleError(problem)
        questions = list(test.approved_questions())
        if len(questions) < MIN_QUESTIONS:
            raise GameRuleError("Тестът още няма достатъчно въпроси.")
        picked = random.SystemRandom().sample(questions, min(test.questions_count, len(questions)))
        allowed = sum(question.time_limit + GRACE_SECONDS for question in picked)
        return Attempt.objects.create(
            test=test, session=session, student=student, secret=secrets.token_hex(16),
            question_ids=[question.pk for question in picked],
            deadline=timezone.now() + timedelta(seconds=allowed * 1.5 + 60),
        )


# ---------- Решаване ----------

def _locked(attempt):
    return Attempt.objects.select_for_update().select_related("test", "student", "session").get(pk=attempt.pk)


def current_question(attempt, now=None):
    """
    Въпросът, който ученикът трябва да види: (въпрос, оставащи секунди) или None, ако е готов.
    Пуска часовника при първото показване; изтекъл въпрос се брои за грешен.
    """
    now = now or timezone.now()
    with transaction.atomic():
        attempt = _locked(attempt)
        while attempt.status == Attempt.Status.RUNNING:
            if attempt.position >= attempt.total or now > attempt.deadline:
                _finish(attempt, now)
                return None
            question = Question.objects.filter(pk=attempt.question_ids[attempt.position]).select_related("test").first()
            if question is None:  # изтрит междувременно – не се брои за грешка
                attempt.question_ids.pop(attempt.position)
                attempt.question_started_at = None
                attempt.save()
                continue
            if attempt.question_started_at is None:
                attempt.question_started_at = now
                attempt.save(update_fields=["question_started_at"])
            left = question.time_limit - (now - attempt.question_started_at).total_seconds()
            if left > -GRACE_SECONDS:
                return question, max(0, left)
            _record(attempt, question, "", False, question.time_limit)
        return None


def _record(attempt, question, value, correct, seconds):
    AttemptAnswer.objects.get_or_create(attempt=attempt, question=question, defaults={
        "value": str(value)[:300], "is_correct": correct, "seconds": round(seconds, 1)})
    attempt.correct += int(correct)
    attempt.position += 1
    attempt.question_started_at = None
    attempt.save(update_fields=["correct", "position", "question_started_at"])


def answer_question(attempt, question_id, value, now=None):
    """Записва отговора. Отговор на друг въпрос (второ натискане, върната страница) се пренебрегва."""
    now = now or timezone.now()
    with transaction.atomic():
        attempt = _locked(attempt)
        if attempt.status != Attempt.Status.RUNNING or attempt.position >= attempt.total:
            return
        if str(attempt.question_ids[attempt.position]) != str(question_id) or attempt.question_started_at is None:
            return
        question = Question.objects.select_related("test").filter(pk=question_id).first()
        if question is None:
            return
        seconds = (now - attempt.question_started_at).total_seconds()
        in_time = seconds <= question.time_limit + GRACE_SECONDS and now <= attempt.deadline
        _record(attempt, question, value, in_time and question.is_correct(value, attempt.secret), seconds)
        if attempt.position >= attempt.total:
            _finish(attempt, now)


def note_left_page(attempt):
    """Ученикът е отворил друг прозорец. Не го наказваме – само учителят го вижда."""
    with transaction.atomic():
        attempt = _locked(attempt)
        if attempt.status == Attempt.Status.RUNNING and attempt.left_page < 99:
            attempt.left_page += 1
            attempt.save(update_fields=["left_page"])


def finish_expired(session):
    """Затваря изоставените опити, за да не остават „в момента“ завинаги."""
    for attempt in session.attempts.filter(status=Attempt.Status.RUNNING, deadline__lt=timezone.now()):
        current_question(attempt)


def _finish(attempt, now):
    test, student = attempt.test, attempt.student
    passed = attempt.total > 0 and attempt.correct * 100 >= test.pass_percent * attempt.total
    attempt.status = Attempt.Status.PASSED if passed else Attempt.Status.FAILED
    attempt.finished_at = now
    if passed and test.is_entry:
        student = User.objects.select_for_update().get(pk=student.pk)
        joined = join_guild(student, test.guild)
        notify(student, Notification.Kind.TEST, f"Мина входния тест с {attempt.percent}% "
               + (f"и вече си в гилдия „{test.guild}“!" if joined else f"за „{test.guild}“, но нямаш място за нова гилдия."),
               link=reverse("guild_list"))
    elif passed and test.guild_id in student.guild_ids:
        before = level_for_xp(xp_total(student))
        award_xp(student, test.xp, reason=f"Месечен тест „{test.title}“"[:255], created_by=attempt.session.teacher, now=now)
        attempt.xp_entry = student.xp_transactions.order_by("-pk").first()
        notify(student, Notification.Kind.TEST, f"Мина месечния тест „{test.title}“ с {attempt.percent}%: +{test.xp} XP.",
               link=reverse("guild_list"))
        after = level_for_xp(xp_total(student))
        if after and after != before:
            notify(student, Notification.Kind.LEVEL_UP, f"Мина на {str(after).lower()}!", link=reverse("home"))
        award_badges(student)
    attempt.save()


def void_attempt(teacher, attempt, why):
    """Учителят анулира опит (напр. преписване): XP и гилдията се връщат, а опитът не се брои."""
    why = (why or "").strip()
    if len(why) < 3:
        raise GameRuleError("Напишете защо анулирате опита.")
    if not (teacher.is_admin_role or attempt.session.teacher_id == teacher.pk):
        raise GameRuleError("Опитът може да анулира само учителят, пуснал теста.")
    with transaction.atomic():
        attempt = _locked(attempt)
        if attempt.status == Attempt.Status.VOID:
            raise GameRuleError("Опитът вече е анулиран.")
        student = User.objects.select_for_update().get(pk=attempt.student_id)
        if attempt.status == Attempt.Status.PASSED:
            if attempt.test.is_entry:
                remove_guild(student, attempt.test.guild_id)
            if attempt.xp_entry and not hasattr(attempt.xp_entry, "reversal"):
                _undo_xp(attempt.xp_entry, teacher, why)
        attempt.status = Attempt.Status.VOID
        attempt.void_reason = why[:200]
        attempt.finished_at = attempt.finished_at or timezone.now()
        attempt.save()
        notify(student, Notification.Kind.UNDONE, f"Опитът ти за „{attempt.test.title}“ е анулиран: {why[:200]}",
               link=reverse("guild_list"))


# ---------- Чернови от асистента ----------

def save_drafts(test, drafts):
    """Записва предложените въпроси като неодобрени. Невалидните се пропускат."""
    from django.core.exceptions import ValidationError

    saved = 0
    for draft in drafts:
        answers = "\n".join(("*" if i == draft["correct"] else "") + str(option).strip().lstrip("*")
                            for i, option in enumerate(draft["options"]))
        question = Question(test=test, text=draft["text"], answers=answers, is_approved=False)
        try:
            question.full_clean()
        except ValidationError:
            continue
        question.save()
        saved += 1
    return saved


def tests_for(student):
    """Всички активни тестове с причината, ако ученикът не може да ги реши сега."""
    tests = GuildTest.objects.filter(is_active=True).select_related("guild")
    return [(test, why_not(student, test)) for test in tests if test.approved_questions().count() >= MIN_QUESTIONS]
