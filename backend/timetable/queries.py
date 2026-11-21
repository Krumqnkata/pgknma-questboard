"""
Справки по разписанието (Ф17 – учители, Ф18 – класове, Ф22 – свободни кабинети).

Функциите връщат обикновени речници. Ползват ги и страницата „Справки“, и API-то,
и асистентът. Правата се проверяват в ensure_allowed() – винаги на сървъра.
"""
from datetime import timedelta

from django.utils import timezone

from accounts.models import SchoolClass

from .models import Lesson, Room

DAY_NAMES = dict(Lesson.Day.choices)            # 0 → „понеделник“
DAY_NUMBERS = {name: number for number, name in DAY_NAMES.items()}

# Справките и кой може да ги ползва
TEACHER_REPORTS = {"teacher_schedule", "teacher_free_periods", "substitutes", "free_rooms"}
CLASS_REPORTS = {"class_schedule"}


class QueryError(Exception):
    """Грешка в справката (непознат учител, ден и т.н.). Текстът се показва на потребителя."""


# ---------- Права ----------

def ensure_allowed(user, report, class_name=None):
    """
    Ф17 и Ф22 – само учители и администратори.
    Ф18 – учители и администратори; ученик само за своя клас.
    """
    if user.is_teacher or user.is_admin_role:
        return
    if user.is_student and report in CLASS_REPORTS:
        if class_name and class_name != str(user.school_class):
            raise QueryError("Учениците могат да правят справка само за своя клас.")
        return
    raise QueryError("Тази справка не е достъпна за вашата роля.")


# ---------- Дни, часове, имена ----------

def now_slot(now=None):
    """Кой ден и кой учебен час е сега (час е None извън часовете)."""
    local = timezone.localtime(now or timezone.now())
    day = local.weekday()
    if day not in DAY_NAMES:
        return {"day": None, "period": None}
    period = (Lesson.objects.filter(day=day, start_time__lte=local.time(), end_time__gte=local.time())
              .values_list("period", flat=True).first())
    return {"day": day, "period": period}


def parse_day(value, now=None):
    """Приема „понеделник“, „днес“, „утре“ или число 0–4. Празно означава днес."""
    if value in (None, ""):
        value = "днес"
    if isinstance(value, int) or str(value).isdigit():
        number = int(value)
    else:
        text = str(value).strip().lower()
        today = timezone.localtime(now or timezone.now())
        if text in ("днес", "сега"):
            number = today.weekday()
        elif text == "утре":
            number = (today + timedelta(days=1)).weekday()
        else:
            number = DAY_NUMBERS.get(text)
    if number not in DAY_NAMES:
        raise QueryError("Разписанието е само за делничните дни (понеделник – петък).")
    return number


def teacher_names():
    return sorted(set(Lesson.objects.values_list("teacher_name", flat=True)))


def resolve_teacher(text):
    """Намира учител по пълно име, по фамилия или по собствено име (без значение от главни букви)."""
    wanted = " ".join(str(text or "").split()).lower()
    if not wanted:
        raise QueryError("Посочете учител.")
    names = teacher_names()
    exact = [name for name in names if name.lower() == wanted]
    if exact:
        return exact[0]
    partial = [name for name in names if wanted in name.lower().split() or wanted in name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise QueryError("Има няколко учители с това име: " + ", ".join(partial) + ". Уточнете.")
    raise QueryError(f"Няма учител „{text}“ в разписанието.")


def resolve_class(text):
    name = str(text or "").strip().upper().replace(" ", "")
    for school_class in SchoolClass.objects.all():
        if school_class.name.upper().replace(" ", "") == name:
            return school_class.name
    raise QueryError(f"Няма клас „{text}“ в разписанието.")


def bell(day):
    """Учебните часове през деня: номер, начало, край."""
    slots = (Lesson.objects.filter(day=day).values("period", "start_time", "end_time")
             .distinct().order_by("period"))
    return [{"period": s["period"], "start": s["start_time"].strftime("%H:%M"),
             "end": s["end_time"].strftime("%H:%M")} for s in slots]


def _lesson(lesson):
    return {
        "day": DAY_NAMES[lesson.day], "period": lesson.period,
        "start": lesson.start_time.strftime("%H:%M"), "end": lesson.end_time.strftime("%H:%M"),
        "class": lesson.school_class.name, "subject": lesson.subject.name,
        "teacher": lesson.teacher_name, "room": lesson.room.name if lesson.room else "",
    }


def _lessons(**filters):
    return Lesson.objects.filter(**filters).select_related("school_class", "subject", "room").order_by("day", "period")


def _slot(day, period, now):
    """Ден и час за справка „сега“: ако не са дадени, се взимат от часовника."""
    day = parse_day(day, now)
    if period in (None, ""):
        current = now_slot(now)
        period = current["period"] if current["day"] == day else None
        if period is None:
            raise QueryError("В момента няма учебен час. Посочете кой час ви интересува.")
    return day, int(period)


# ---------- Ф17: учители ----------

def teacher_schedule(teacher, day=None, now=None):
    """Кога има часове учителят (за ден или за цялата седмица)."""
    name = resolve_teacher(teacher)
    filters = {"teacher_name": name}
    if day not in (None, ""):
        filters["day"] = parse_day(day, now)
    return {"teacher": name, "day": DAY_NAMES.get(filters.get("day")), "lessons": [_lesson(x) for x in _lessons(**filters)]}


def teacher_free_periods(teacher, day=None, now=None):
    """Кои часове през деня учителят е свободен."""
    name = resolve_teacher(teacher)
    day = parse_day(day, now)
    busy = set(Lesson.objects.filter(teacher_name=name, day=day).values_list("period", flat=True))
    return {"teacher": name, "day": DAY_NAMES[day], "free_periods": [s for s in bell(day) if s["period"] not in busy]}


def substitutes(teacher, day=None, period=None, now=None):
    """Кой може да замести учителя: свободните в този час, първо тези със същия предмет."""
    name = resolve_teacher(teacher)
    day, period = _slot(day, period, now)
    lesson = _lessons(teacher_name=name, day=day, period=period).first()
    busy = set(Lesson.objects.filter(day=day, period=period).values_list("teacher_name", flat=True))
    free = [t for t in teacher_names() if t not in busy and t != name]
    same_subject = []
    if lesson:
        teaches_subject = set(Lesson.objects.filter(subject=lesson.subject).values_list("teacher_name", flat=True))
        same_subject = [t for t in free if t in teaches_subject]
    return {
        "teacher": name, "day": DAY_NAMES[day], "period": period,
        "lesson": _lesson(lesson) if lesson else None,
        "same_subject": same_subject,
        "other_free": [t for t in free if t not in same_subject],
    }


# ---------- Ф18: класове ----------

def class_schedule(class_name, day=None, period=None, now=None):
    """Какви часове има класът (за ден или само за един час) и в кой кабинет."""
    name = resolve_class(class_name)
    day = parse_day(day, now)
    filters = {"school_class__name": name, "day": day}
    if period not in (None, ""):
        filters["period"] = int(period)
    return {"class": name, "day": DAY_NAMES[day], "period": filters.get("period"),
            "lessons": [_lesson(x) for x in _lessons(**filters)]}


def class_now(class_name, now=None):
    """Къде е класът в момента."""
    current = now_slot(now)
    if current["period"] is None:
        name = resolve_class(class_name)
        return {"class": name, "now": None, "message": "В момента няма учебни часове."}
    return class_schedule(class_name, current["day"], current["period"], now)


# ---------- Ф22: свободни кабинети ----------

def free_rooms(day=None, period=None, now=None):
    day, period = _slot(day, period, now)
    used = set(Lesson.objects.filter(day=day, period=period, room__isnull=False).values_list("room_id", flat=True))
    rooms = Room.objects.exclude(id__in=used).order_by("name")
    return {"day": DAY_NAMES[day], "period": period, "rooms": [room.name for room in rooms]}


# ---------- Обща входна точка ----------

def run_report(user, report, params):
    """
    Проверява правата и изпълнява справката по име.
    Ползват я страницата „Справки“, API-то и асистентът.
    """
    params = dict(params)
    if user.is_student and not params.get("class_name"):
        params["class_name"] = str(user.school_class)  # ученикът – по подразбиране своя клас
    ensure_allowed(user, report, params.get("class_name"))
    if report == "teacher_schedule":
        return teacher_schedule(params.get("teacher"), params.get("day"))
    if report == "teacher_free_periods":
        return teacher_free_periods(params.get("teacher"), params.get("day"))
    if report == "substitutes":
        return substitutes(params.get("teacher"), params.get("day"), params.get("period"))
    if report == "class_schedule":
        return class_schedule(params.get("class_name"), params.get("day"), params.get("period"))
    if report == "free_rooms":
        return free_rooms(params.get("day"), params.get("period"))
    raise QueryError("Непозната справка.")
