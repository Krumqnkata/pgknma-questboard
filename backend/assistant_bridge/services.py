"""
Асистентът от страната на Django: подсказки (Ф10), чернови на мисии (Ф11)
и справки (Ф17, Ф18, Ф22, Ф14).

Правила от раздел 3.2 на плана, които се спазват тук:
  - асистентът може да се изключи от admin – платформата работи и без него;
  - всяко ползване се записва в журнала (кой, кога, по коя мисия);
  - има дневен лимит на заявките на потребител;
  - при грешка на модела Hint Token-ът НЕ се харчи;
  - към модела не се изпращат имена на ученици, а имената на учителите се заменят с кодове.
"""
import time
from dataclasses import dataclass, field

from django.utils import timezone

from accounts.models import Guild
from economy.models import GameSettings, Purchase
from missions.services import GameRuleError
from timetable import queries

from . import client
from .models import AssistantLog, Hint
from .pseudonyms import TeacherCodes
from .tools import run_tool, tools_for

HINT_TOKEN = "hint_token"


class AssistantError(Exception):
    """Асистентът не може да помогне сега. Текстът се показва на потребителя."""


# ---------- Общи проверки и журнал ----------

def _check_available(user):
    rules = GameSettings.load()
    if not rules.assistant_enabled:
        raise AssistantError("Асистентът е изключен от администратора. Всичко останало работи.")
    used_today = AssistantLog.objects.filter(user=user, created_at__date=timezone.localdate()).count()
    if used_today >= rules.assistant_daily_limit:
        raise AssistantError(f"Достигнахте дневния лимит от {rules.assistant_daily_limit} заявки към асистента.")


class _Logged:
    """Записва в журнала колко е продължила заявката и дали е успешна."""

    def __init__(self, user, kind, mission=None):
        self.entry = AssistantLog(user=user, kind=kind, mission=mission)
        self.started = time.monotonic()

    def finish(self, success, error=""):
        self.entry.success = success
        self.entry.error = str(error)[:255]
        self.entry.duration_ms = int((time.monotonic() - self.started) * 1000)
        self.entry.save()


def _call(log, path, payload):
    try:
        return client.call(path, payload)
    except client.AssistantUnavailable as error:
        log.finish(False, error)
        raise AssistantError(str(error))


# ---------- Ф10: подсказка срещу Hint Token ----------

def unused_hint_tokens(student):
    return Purchase.objects.filter(student=student, privilege__code=HINT_TOKEN, used_at__isnull=True)


def request_hint(student, mission):
    """
    Дава подсказка по мисия и харчи един Hint Token.
    Токенът се отбелязва като използван САМО след успешен отговор от асистента.
    """
    if not student.is_student:
        raise GameRuleError("Подсказки могат да искат само ученици.")
    if not mission.hints_allowed:
        raise GameRuleError("Учителят е забранил подсказките за тази мисия.")
    if not mission.is_open():
        raise GameRuleError("Мисията вече не е активна.")
    if not unused_hint_tokens(student).exists():
        raise GameRuleError("Нямаш Hint Token. Можеш да купиш от магазина.")
    _check_available(student)

    log = _Logged(student, AssistantLog.Kind.HINT, mission)
    # Към модела отиват само текстовете на мисията – без данни за ученика.
    answer = _call(log, "/hint", {"mission": {
        "title": mission.title, "description": mission.description, "criteria": mission.criteria,
    }})

    # Отговорът е получен – чак сега харчим токена. Условната промяна (само ако още
    # е неизползван) пази от двойно харчене при две едновременни заявки.
    for token in unused_hint_tokens(student).order_by("purchased_at"):
        spent = Purchase.objects.filter(pk=token.pk, used_at__isnull=True).update(
            used_at=timezone.now(), used_for_mission=mission)
        if spent:
            log.finish(True)
            return Hint.objects.create(student=student, mission=mission, purchase=token, text=answer["hint"])

    log.finish(False, "няма неизползван Hint Token")
    raise GameRuleError("Hint Token-ът вече е използван.")


# ---------- Ф11: чернова на мисия ----------

def draft_mission(teacher, idea):
    """Връща попълнена чернова за формата. Нищо не се публикува без учителя."""
    if not teacher.is_teacher:
        raise GameRuleError("Чернови могат да правят само учители.")
    idea = (idea or "").strip()
    if len(idea) < 5:
        raise GameRuleError("Опишете идеята с поне едно изречение.")
    _check_available(teacher)

    log = _Logged(teacher, AssistantLog.Kind.MISSION_DRAFT)
    guilds = list(Guild.objects.all())
    draft = _call(log, "/mission-draft", {
        "idea": idea[:1000],
        "guilds": [{"name": g.name, "description": g.description} for g in guilds],
        "max_xp": GameSettings.load().max_xp_per_mission,
    })
    log.finish(True)

    guild = next((g for g in guilds if g.name == draft["guild"]), None)
    return {
        "title": draft["title"], "description": draft["description"], "criteria": draft["criteria"],
        "guild": guild.pk if guild else None, "xp": draft["xp"],
    }


# ---------- Справки с извикване на функции ----------

@dataclass
class Answer:
    text: str
    tool: str | None = None
    data: dict = field(default_factory=dict)


def ask(user, question):
    """
    1) моделът избира справка (вижда само кодове вместо имената на учителите);
    2) Django я изпълнява с правата на потребителя;
    3) моделът оформя отговора само от върнатите данни.
    """
    question = (question or "").strip()[:500]
    if not question:
        raise GameRuleError("Напишете въпрос.")
    _check_available(user)

    log = _Logged(user, AssistantLog.Kind.QUERY)
    codes = TeacherCodes(queries.teacher_names())
    hidden_question = codes.hide(question)
    current = queries.now_slot()

    plan = _call(log, "/query/plan", {
        "question": hidden_question,
        "tools": tools_for(user),
        "context": {
            "today": queries.DAY_NAMES.get(current["day"], "почивен ден"),
            "now_period": str(current["period"] or ""),
            "role": user.get_role_display(),
        },
    })
    if not plan.get("tool"):
        log.finish(True)
        return Answer(text=codes.reveal(plan.get("answer") or ""))

    try:
        data = run_tool(user, plan["tool"], codes.reveal_data(plan.get("arguments") or {}))
    except queries.QueryError as error:
        # Грешката е за потребителя (непознат учител, няма права и т.н.) – не я пращаме към модела.
        log.finish(True)
        return Answer(text=str(error), tool=plan["tool"])

    result = _call(log, "/query/answer", {"question": hidden_question, "tool": plan["tool"],
                                         "data": codes.hide_data(data)})
    log.finish(True)
    return Answer(text=codes.reveal(result["answer"]), tool=plan["tool"], data=data)
