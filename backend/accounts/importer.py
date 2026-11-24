"""
Внасяне на ученици и учители от CSV файл.

Форматът (първият ред е заглавен, разделител запетая или точка и запетая):

    имейл,име,фамилия,роля,псевдоним,клас,гилдия
    ivan.petrov@example.bg,Иван,Петров,ученик,Сокол,11Б,Изследователи
    m.ivanova@example.bg,Мария,Иванова,учител,,,

Ролята е „ученик“ или „учител“. Администратори не се внасят от файл – само ръчно.
За учениците псевдонимът, класът и гилдията са задължителни.

Всеки нов потребител получава случайна временна парола, която трябва да смени
при първия вход. Паролите се връщат САМО веднъж – за да ги раздаде администраторът.
В базата се пази само хешът им. Ако има грешка дори на един ред, нищо не се внася.
"""
import secrets
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from questboard.csv_utils import read_csv_rows

from .models import Guild, SchoolClass, User

COLUMNS = ["имейл", "име", "фамилия", "роля", "псевдоним", "клас", "гилдия"]
ROLES = {"ученик": User.Role.STUDENT, "учител": User.Role.TEACHER}

# Без букви и цифри, които лесно се бъркат (l, 1, O, 0) – паролата се преписва от лист.
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 10


def temporary_password():
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


@dataclass
class CreatedUser:
    email: str
    name: str
    role: str
    nickname: str
    school_class: str
    password: str


@dataclass
class ImportResult:
    created: list[CreatedUser] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # имейли, които вече съществуват
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


def _parse_rows(rows, result):
    """Проверява всички редове. Връща списък с готови за запис данни."""
    guilds = {guild.name.lower(): guild for guild in Guild.objects.all()}
    existing_emails = {email.lower() for email in User.objects.values_list("email", flat=True)}
    existing_nicknames = {n.lower() for n in User.objects.exclude(nickname=None).values_list("nickname", flat=True)}
    seen_emails, seen_nicknames = set(), set()
    parsed = []

    for number, row in enumerate(rows, start=2):  # ред 1 е заглавният
        values = {column: (row.get(column) or "").strip() for column in COLUMNS}
        email = values["имейл"].lower()

        try:
            validate_email(email)
        except ValidationError:
            result.errors.append(f"Ред {number}: невалиден имейл „{values['имейл']}“.")
            continue
        if email in seen_emails:
            result.errors.append(f"Ред {number}: имейлът {email} се повтаря във файла.")
            continue
        seen_emails.add(email)
        if email in existing_emails:
            result.skipped.append(email)
            continue

        role = ROLES.get(values["роля"].lower())
        if role is None:
            result.errors.append(f"Ред {number}: ролята трябва да е „ученик“ или „учител“.")
            continue
        if not values["име"] or not values["фамилия"]:
            result.errors.append(f"Ред {number}: липсва име или фамилия.")
            continue

        data = {"email": email, "first_name": values["име"], "last_name": values["фамилия"], "role": role,
                "nickname": None, "class_name": "", "guild": None}

        if role == User.Role.STUDENT:
            nickname = values["псевдоним"]
            guild = guilds.get(values["гилдия"].lower())
            if not nickname or not values["клас"]:
                result.errors.append(f"Ред {number}: за ученик са нужни псевдоним и клас.")
                continue
            if guild is None and values["гилдия"]:  # празно – ученикът влиза с входен тест
                result.errors.append(f"Ред {number}: непозната гилдия „{values['гилдия']}“ "
                                     f"(възможни: {', '.join(g.name for g in guilds.values())}).")
                continue
            if nickname.lower() in existing_nicknames or nickname.lower() in seen_nicknames:
                result.errors.append(f"Ред {number}: псевдонимът „{nickname}“ вече е зает.")
                continue
            seen_nicknames.add(nickname.lower())
            data.update(nickname=nickname, class_name=values["клас"], guild=guild)

        parsed.append(data)
    return parsed


def import_users(text):
    """Създава потребителите от CSV текста. Съществуващите имейли се пропускат."""
    result = ImportResult()
    rows = read_csv_rows(text)
    if not rows:
        result.errors.append("Файлът е празен.")
        return result

    missing = [column for column in COLUMNS if column not in rows[0]]
    if missing:
        result.errors.append("Липсват колони: " + ", ".join(missing) + ". Очакват се: " + ",".join(COLUMNS))
        return result

    parsed = _parse_rows(rows, result)
    if result.errors:
        result.skipped.clear()
        return result

    with transaction.atomic():
        for data in parsed:
            password = temporary_password()
            school_class = None
            if data["class_name"]:
                school_class = SchoolClass.objects.get_or_create(name=data["class_name"])[0]
            User.objects.create_user(
                data["email"], password,
                first_name=data["first_name"], last_name=data["last_name"], role=data["role"],
                nickname=data["nickname"], school_class=school_class, guild=data["guild"],
                must_change_password=True,
            )
            result.created.append(CreatedUser(
                email=data["email"], name=f"{data['first_name']} {data['last_name']}",
                role=User.Role(data["role"]).label, nickname=data["nickname"] or "",
                school_class=data["class_name"], password=password,
            ))
    return result
