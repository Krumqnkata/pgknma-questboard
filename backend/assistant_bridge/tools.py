"""
Справките, които асистентът може да „извика“ (извикване на функции).

Езиковият модел не вижда базата. Той само избира една от тези справки и
попълва параметрите ѝ. Django я изпълнява с правата на питащия
(timetable.queries.run_report проверява ролята) и чак тогава моделът
оформя отговора от върнатите данни.
"""
from django.utils import timezone

from economy.services import student_stats
from missions.models import Claim
from missions.services import missions_for_student
from timetable import queries


def _schema(**properties):
    """Схема на параметрите. Всички са задължителни (строг режим); празен текст означава „по подразбиране“."""
    return {
        "type": "object",
        "properties": {name: {"type": "string", "description": text} for name, text in properties.items()},
        "required": list(properties),
        "additionalProperties": False,
    }


DAY = "ден: понеделник … петък, „днес“, „утре“ или празно за днес"
PERIOD = "номер на учебния час (напр. „3“) или празно за текущия час"
TEACHER = "кодът на учителя, напр. „Учител-3“"

TOOLS = {
    "teacher_schedule": {
        "description": "Кога има часове даден учител – за един ден или за цялата седмица (Ф17).",
        "parameters": _schema(teacher=TEACHER, day="ден или празно за цялата седмица"),
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
    """Изпълнява избраната справка с правата на потребителя."""
    allowed = {tool["name"] for tool in tools_for(user)}
    if name not in allowed:
        raise queries.QueryError("Тази справка не е достъпна за вашата роля.")
    if name == "my_progress":
        return my_progress(user)
    return queries.run_report(user, name, arguments)


def my_progress(student):
    """Данни за Ф14 – без име и псевдоним, само числа и мисии."""
    stats = student_stats(student)
    claimed = set(Claim.objects.filter(student=student).values_list("mission_id", flat=True))
    open_missions = [m for m in missions_for_student().order_by("-xp") if m.id not in claimed][:5]
    return {
        "xp": stats.xp,
        "level": stats.level.number if stats.level else None,
        "next_level": stats.next_level.number if stats.next_level else None,
        "xp_to_next_level": stats.xp_to_next_level,
        "coins": stats.coins,
        "coins_this_week": stats.coins_this_week,
        "weekly_coin_limit": stats.weekly_limit,
        "open_missions": [
            {"title": m.title, "guild": m.guild.name, "xp": m.xp,
             "deadline": timezone.localtime(m.deadline).strftime("%d.%m %H:%M")}
            for m in open_missions
        ],
    }
