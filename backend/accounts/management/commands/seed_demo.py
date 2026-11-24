"""
Зарежда примерни данни: класове, тестови акаунти за всяка роля, няколко мисии
и примерно седмично разписание.

    python manage.py seed_demo

Всички хора са измислени. Паролата на тестовите акаунти се взема от
DEMO_PASSWORD в .env, за да не стои в кода. Командата може да се пуска
многократно: не създава дубликати, а обновява паролите.
"""
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Guild, SchoolClass, User
from missions.models import Mission
from timetable.importer import import_timetable
from timetable.models import Lesson

SAMPLE_TIMETABLE = Path(settings.BASE_DIR) / "timetable" / "sample" / "razpisanie_primer.csv"

CLASSES = ["10А", "11Б"]

ADMIN = {"email": "admin@questboard.test", "first_name": "Администратор", "last_name": "Демо"}
TEACHER = {"email": "uchitel@questboard.test", "first_name": "Елена", "last_name": "Маринова"}

# (имейл, име, фамилия, псевдоним, клас, гилдия)
STUDENTS = [
    ("uchenik@questboard.test", "Калина", "Петкова", "Феникс", "11Б", "Техничари"),
    ("uchenik2@questboard.test", "Борис", "Стоянов", "Сокол", "11Б", "Изследователи"),
    ("uchenik3@questboard.test", "Мила", "Илиева", "Комета", "10А", "Помощници"),
    ("uchenik4@questboard.test", "Даниел", "Колев", "Вихър", "10А", "Организатори"),
]

# (заглавие, гилдия, XP, след колко дни е срокът, описание, критерий)
MISSIONS = [
    ("Помощник в компютърния кабинет", "Техничари", 60, 14,
     "Помогни при подготовката на компютрите за общоучилищното състезание.",
     "Учителят по информатика потвърждава, че си присъствал поне 2 часа."),
    ("Репортаж от училищното събитие", "Изследователи", 40, 10,
     "Направи кратък репортаж (текст и снимки) от най-близкото училищно събитие.",
     "Връзка към публикуван репортаж в сайта или училищния вестник."),
    ("Наставник по математика", "Помощници", 80, 21,
     "Помогни на ученик от по-долен клас с подготовката за контролно.",
     "Поне три срещи, потвърдени от класния ръководител."),
    ("Идея за по-зелено училище", "Организатори", 30, 7,
     "Предложи конкретна идея за намаляване на отпадъците в училище.",
     "Идеята е описана в поне 150 думи и е представена на ученическия съвет."),
]


class Command(BaseCommand):
    help = "Зарежда примерни класове, тестови акаунти и мисии (само измислени хора)."

    def handle(self, *args, **options):
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 8:
            raise CommandError("Сложете DEMO_PASSWORD в .env (поне 8 символа).")

        classes = {name: SchoolClass.objects.get_or_create(name=name)[0] for name in CLASSES}
        guilds = {guild.name: guild for guild in Guild.objects.all()}

        self.save_user(password, role=User.Role.ADMIN, **ADMIN)
        teacher = self.save_user(password, role=User.Role.TEACHER, **TEACHER)

        for email, first_name, last_name, nickname, class_name, guild_name in STUDENTS:
            self.save_user(
                password, email=email, first_name=first_name, last_name=last_name, role=User.Role.STUDENT,
                nickname=nickname, school_class=classes[class_name], guild=guilds[guild_name],
            )

        now = timezone.now()
        for title, guild_name, xp, days, description, criteria in MISSIONS:
            Mission.objects.get_or_create(title=title, created_by=teacher, defaults={
                "guild": guilds[guild_name], "xp": xp, "deadline": now + timedelta(days=days),
                "description": description, "criteria": criteria,
            })

        # Примерно разписание с измислени учители – само ако още няма внесено истинско
        if not Lesson.objects.exists():
            timetable = import_timetable(SAMPLE_TIMETABLE.read_text(encoding="utf-8"))
            if not timetable.ok:
                raise CommandError("Примерното разписание има грешки: " + "; ".join(timetable.errors))

        self.stdout.write(self.style.SUCCESS("Примерните данни са заредени. Тестови акаунти:"))
        for email in [ADMIN["email"], TEACHER["email"]] + [s[0] for s in STUDENTS]:
            self.stdout.write(f"  {email}")
        self.stdout.write("Паролата е стойността на DEMO_PASSWORD от .env.")

    def save_user(self, password, email, **fields):
        user = User.objects.filter(email=email).first() or User(email=email)
        for name, value in fields.items():
            setattr(user, name, value)
        user.set_password(password)
        user.full_clean()
        user.save()
        return user
