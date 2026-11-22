"""
Внасяне на седмичното разписание от CSV файл.

Форматът (първият ред е заглавен, разделител запетая или точка и запетая):

    ден,час,начало,край,клас,предмет,учител,кабинет
    понеделник,1,08:00,08:40,11Б,Математика,Петър Николов,203

Пример: timetable/sample/razpisanie_primer.csv. Ако има поне една грешка,
нищо не се внася, а се връща списък с грешките и номерата на редовете.
"""
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction

from accounts.models import SchoolClass, User
from questboard.csv_utils import read_csv_rows

from .models import Lesson, Room, Subject

COLUMNS = ["ден", "час", "начало", "край", "клас", "предмет", "учител", "кабинет"]

DAYS = {
    "понеделник": Lesson.Day.MONDAY,
    "вторник": Lesson.Day.TUESDAY,
    "сряда": Lesson.Day.WEDNESDAY,
    "четвъртък": Lesson.Day.THURSDAY,
    "петък": Lesson.Day.FRIDAY,
}


@dataclass
class ImportResult:
    created: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def _parse_time(value):
    return datetime.strptime(value.strip(), "%H:%M").time()


def _parse_row(number, row):
    """Проверява един ред. Връща (данни, None) или (None, грешка)."""
    values = {column: (row.get(column) or "").strip() for column in COLUMNS}
    missing = [column for column in COLUMNS if column != "кабинет" and not values[column]]
    if missing:
        return None, f"Ред {number}: липсва {', '.join(missing)}."

    day = DAYS.get(values["ден"].lower())
    if day is None:
        return None, f"Ред {number}: непознат ден „{values['ден']}“ (очаква се понеделник … петък)."
    if not values["час"].isdigit() or not 1 <= int(values["час"]) <= 14:
        return None, f"Ред {number}: часът трябва да е число от 1 до 14."
    try:
        start, end = _parse_time(values["начало"]), _parse_time(values["край"])
    except ValueError:
        return None, f"Ред {number}: часовете трябва да са във вида 08:00."
    if start >= end:
        return None, f"Ред {number}: началото трябва да е преди края."

    return {
        "day": day, "period": int(values["час"]), "start_time": start, "end_time": end,
        "class_name": values["клас"], "subject": values["предмет"],
        "teacher_name": " ".join(values["учител"].split()), "room": values["кабинет"],
    }, None


def import_timetable(text):
    """Заменя цялото разписание с това от CSV текста."""
    result = ImportResult()
    rows = read_csv_rows(text)
    if not rows:
        result.errors.append("Файлът е празен.")
        return result

    header_missing = [column for column in COLUMNS if column not in rows[0]]
    if header_missing:
        result.errors.append("Липсват колони: " + ", ".join(header_missing) + ". Очакват се: " + ",".join(COLUMNS))
        return result

    parsed = []
    for number, row in enumerate(rows, start=2):  # ред 1 е заглавният
        data, error = _parse_row(number, row)
        if error:
            result.errors.append(error)
        else:
            parsed.append(data)
    if result.errors:
        return result

    # Учителите с акаунт се свързват по име и фамилия.
    accounts = {user.get_full_name(): user for user in User.objects.filter(role=User.Role.TEACHER)}

    with transaction.atomic():
        Lesson.objects.all().delete()
        for data in parsed:
            Lesson.objects.create(
                day=data["day"], period=data["period"], start_time=data["start_time"], end_time=data["end_time"],
                school_class=SchoolClass.objects.get_or_create(name=data["class_name"])[0],
                subject=Subject.objects.get_or_create(name=data["subject"])[0],
                teacher_name=data["teacher_name"],
                teacher=accounts.get(data["teacher_name"]),
                room=Room.objects.get_or_create(name=data["room"])[0] if data["room"] else None,
            )
            result.created += 1
    return result
