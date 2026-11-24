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
from badges.models import Badge
from economy.models import GameSettings, Purchase
from missions.models import TEAM_LIMIT
from missions.services import GameRuleError
from timetable import queries

from . import client
from .models import AssistantLog, Hint
from .pseudonyms import TeacherCodes
from .site_tools import visible_links
from .tools import run_tool, tools_for

HINT_TOKEN = "hint_token"
HISTORY_MESSAGES = 6     # последните три въпроса с отговорите им
HISTORY_CHARS = 400


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

    def finish(self, success, error="", provider=""):
        self.entry.success = success
        self.entry.provider = provider or self.entry.provider
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
            log.finish(True, provider=answer.get("provider", ""))
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
    badges = list(Badge.objects.filter(rule=Badge.Rule.MISSION, is_active=True))
    draft = _call(log, "/mission-draft", {
        "idea": idea[:1000],
        "guilds": [{"name": g.name, "description": g.description} for g in guilds],
        "max_xp": GameSettings.load().max_xp_per_mission,
        "badges": [{"name": b.name, "description": b.description} for b in badges],
        "team_limit": TEAM_LIMIT,
    })
    log.finish(True, provider=draft.get("provider", ""))

    guild = next((g for g in guilds if g.name == draft["guild"]), None)
    return {
        "title": draft["title"], "description": draft["description"], "criteria": draft["criteria"],
        "guild": guild.pk if guild else None, "xp": draft["xp"],
        "is_group": draft.get("is_group", False),
        "team_min": draft.get("team_min", 2), "team_max": draft.get("team_max", 4),
        "reward_badge": next((b.pk for b in badges if b.name == draft.get("badge")), None),
    }


# ---------- Справки с извикване на функции ----------

@dataclass
class Answer:
    text: str
    tool: str | None = None
    data: dict = field(default_factory=dict)
    links: list = field(default_factory=list)  # [{"label", "url"}] – адресите са от сървъра


def _clean_history(history, codes):
    """
    Последните реплики, за да разбере моделът „а в четвъртък?“. Идват от браузъра и не се пазят
    на сървъра. Имената на учителите и тук се заменят с кодове. Правата не зависят от тях:
    всяка справка пак се изпълнява с правата на питащия.
    """
    return [{"role": item["role"], "text": codes.hide(str(item["text"])[:HISTORY_CHARS])}
            for item in list(history or [])[-HISTORY_MESSAGES:]
            if item.get("role") in ("user", "assistant") and str(item.get("text", "")).strip()]


def ask(user, question, history=()):
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
    hidden_history = _clean_history(history, codes)
    current = queries.now_slot()

    plan = _call(log, "/query/plan", {
        "question": hidden_question,
        "history": hidden_history,
        "tools": tools_for(user),
        "context": {
            "today": queries.DAY_NAMES.get(current["day"], "почивен ден"),
            "now_period": str(current["period"] or ""),
            "role": user.get_role_display(),
        },
    })
    log.entry.provider = plan.get("provider", "")
    if not plan.get("tool"):
        log.finish(True)
        return Answer(text=codes.reveal(plan.get("answer") or ""))

    try:
        found = run_tool(user, plan["tool"], codes.reveal_data(plan.get("arguments") or {}))
    except queries.QueryError as error:
        # Грешката е за потребителя (непознат учител, няма права и т.н.) – не я пращаме към модела.
        log.finish(True)
        return Answer(text=str(error), tool=plan["tool"])

    result = _call(log, "/query/answer", {"question": hidden_question, "tool": plan["tool"],
                                         "data": codes.hide_data(found.data), "history": hidden_history})
    log.finish(True, provider=result.get("provider", ""))
    text = codes.reveal(result["answer"])
    return Answer(text=text, tool=plan["tool"], data=found.data, links=visible_links(found.links, text))


# ---------- Проверка на системата (само за администратора) ----------

def explain_problems(admin, problems):
    """
    Обяснява намерените проблеми и кой е най-важен. Моделът вижда само вида и броя им.
    Нищо не поправя – поправките са бутони в questboard/diagnostics.py.
    """
    if not admin.is_admin_role:
        raise GameRuleError("Проверката на системата е само за администратори.")
    if not problems:
        raise GameRuleError("Няма намерени проблеми.")
    _check_available(admin)
    log = _Logged(admin, AssistantLog.Kind.DIAGNOSE)
    result = _call(log, "/diagnose", {"problems": [
        {"title": item.title, "count": item.count, "advice": item.advice, "fix": item.fix_label}
        for item in problems
    ]})
    log.finish(True, provider=result.get("provider", ""))
    return result["answer"]
