"""
Справките, които асистентът може да „извика“ (извикване на функции).

Езиковият модел не вижда базата. Той само избира една от тези справки и
попълва параметрите ѝ. Django я изпълнява с правата на питащия
(timetable.queries.run_report проверява ролята) и чак тогава моделът
оформя отговора от върнатите данни.
"""
from django.urls import reverse
from django.utils import timezone

from economy.services import student_stats
from missions.models import Claim
from missions.services import missions_for_student
from timetable import queries

from . import site_tools
from .site_tools import Link, ToolResult


def _schema(**properties):
    """Схема на параметрите. Всички са задължителни (строг режим); празен текст означава „по подразбиране“."""
    return {
        "type": "object",
        "properties": {name: {"type": "string", **(value if isinstance(value, dict) else {"description": value})}
                       for name, value in properties.items()},
        "required": list(properties),
        "additionalProperties": False,
    }


# Денят е затворен списък, за да не може моделът да го напише грешно (напр. на руски – „среда“).
DAYS = ["днес", "утре", *queries.DAY_NAMES.values()]
WHOLE_WEEK = "цялата седмица"
ALL = "всички"
DAY = {"description": "ден от седмицата; „днес“, ако не е посочен", "enum": DAYS}
PERIOD = "номер на учебния час (напр. „3“) или празно за текущия час"
TEACHER = "кодът на учителя, напр. „Учител-3“"

TOOLS = {
    "teacher_schedule": {
        "description": "Кога има часове даден учител – за един ден или за цялата седмица (Ф17).",
        "parameters": _schema(teacher=TEACHER, day={"description": "ден; „цялата седмица“, ако не е посочен", "enum": [WHOLE_WEEK, *DAYS]}),
        "for_students": False,
    },
    "teacher_free_periods": {
        "description": "В кои часове през деня даден учител е свободен (Ф17).",
        "parameters": _schema(teacher=TEACHER, day=DAY),
        "for_students": False,
    },
    "substitutes": {
        "description": "Кои учители са свободни и могат да заместят даден учител в определен час (Ф17).",
        "parameters": _schema(teacher=TEACHER, day=DAY, period=PERIOD),
        "for_students": False,
    },
    "class_schedule": {
        "description": "Какви часове има даден клас и в кой кабинет – за ден или за един час (Ф18).",
        "parameters": _schema(class_name="клас, напр. „11Б“ (за ученик – празно е неговият клас)",
                              day=DAY, period="номер на час или празно за целия ден"),
        "for_students": True,
    },
    "free_rooms": {
        "description": "Кои кабинети са свободни в даден час (Ф22).",
        "parameters": _schema(day=DAY, period=PERIOD),
        "for_students": False,
    },
    "my_progress": {
        "description": "Напредъкът на питащия ученик: ниво, колко XP остават до следващото, монети и "
                       "активни мисии, които още не е заявил (Ф14).",
        "parameters": _schema(),
        "for_students": True,
        "only_students": True,
    },
    # ---------- За самия сайт (site_tools.py) ----------
    "open_missions": {
        "description": "Активните мисии и домашни, които питащият ученик още не е заявил: заглавие, гилдия, XP, срок, отбор и "
                       "специална награда. За „коя мисия да избера“ и „има ли отборни мисии“.",
        "parameters": _schema(guild="име на гилдия само ако потребителят сам я назове в този въпрос, иначе празно",
                              kind={"description": "вид на мисиите", "enum": [ALL, "отборни", "индивидуални", "домашни"]}),
        "for_students": True, "only_students": True, "run": site_tools.open_missions,
    },
    "my_claims": {
        "description": "Заявките на питащия ученик и дали са потвърдени, отказани или чакат.",
        "parameters": _schema(), "for_students": True, "only_students": True, "run": site_tools.my_claims,
    },
    "shop": {
        "description": "Магазинът: привилегии, награди от партньори, титли и рамки, с цена, бройки и ниво, и какво може "
                       "да купи питащият ученик сега.",
        "parameters": _schema(), "for_students": True, "only_students": True, "run": site_tools.shop,
    },
    "my_badges": {
        "description": "Значките на питащия ученик и до кои е най-близо.",
        "parameters": _schema(), "for_students": True, "only_students": True, "run": site_tools.my_badges,
    },
    "ranking": {
        "description": "Класацията на гилдиите и класовете и мястото на питащия ученик.",
        "parameters": _schema(), "for_students": True, "run": site_tools.ranking,
    },
    "game_rules": {
        "description": "Правилата на играта: как се печелят XP и монети, седмичен лимит, нива, карти, заявки, отбори, "
                       "файлове, серии, псевдоними. За всеки въпрос „как работи“.",
        "parameters": _schema(), "for_students": True, "run": site_tools.game_rules,
    },
    "my_missions": {
        "description": "Мисиите на питащия учител (и тези, на които е заместник): срок, чакащи и потвърдени заявки.",
        "parameters": _schema(), "for_students": False, "run": site_tools.my_missions,
    },
    "pending_reviews": {
        "description": "Колко заявки чакат проверка от питащия учител, по мисии и от колко дни.",
        "parameters": _schema(), "for_students": False, "run": site_tools.pending_reviews,
    },
    "to_hand_over": {
        "description": "Колко купени привилегии и награди от партньори чакат да бъдат предадени на учениците.",
        "parameters": _schema(), "for_students": False, "run": site_tools.to_hand_over,
    },
}


def tools_for(user):
    """Справките, разрешени за ролята на потребителя."""
    result = []
    for name, tool in TOOLS.items():
        if user.is_student and not tool["for_students"]:
            continue
        if not user.is_student and tool.get("only_students"):
            continue
        result.append({"name": name, "description": tool["description"], "parameters": tool["parameters"]})
    return result


def run_tool(user, name, arguments):
    """Изпълнява избраната справка с правата на потребителя. Връща ToolResult: данни и връзки."""
    allowed = {tool["name"] for tool in tools_for(user)}
    if name not in allowed:
        raise queries.QueryError("Тази справка не е достъпна за вашата роля.")
    arguments = {key: "" if value == WHOLE_WEEK else value for key, value in arguments.items()}
    if name == "my_progress":
        return ToolResult(my_progress(user), [Link("Към мисиите", reverse("mission_list"))])
    if "run" in TOOLS[name]:
        return TOOLS[name]["run"](user, arguments)
    links = [] if user.is_student else [Link("Всички справки", reverse("reports"))]
    return ToolResult(queries.run_report(user, name, arguments), links)


def my_progress(student):
    """Данни за Ф14 – без име и псевдоним, само числа и мисии."""
    stats = student_stats(student)
    claimed = set(Claim.objects.filter(student=student).values_list("mission_id", flat=True))
    open_missions = [m for m in missions_for_student(student).order_by("-xp") if m.id not in claimed][:5]
    return {
        "xp": stats.xp,
        "level": stats.level.number if stats.level else None,
        "next_level": stats.next_level.number if stats.next_level else None,
        "xp_to_next_level": stats.xp_to_next_level,
        "coins": stats.coins,
        "coins_this_week": stats.coins_this_week,
        "weekly_coin_limit": stats.weekly_limit,
        "open_missions": [
            {"title": m.title, "guild": m.source, "xp": m.xp,
             "deadline": timezone.localtime(m.deadline).strftime("%d.%m %H:%M")}
            for m in open_missions
        ],
    }
