"""Помощни функции за тестовете – създават потребители и мисии с минимум код."""
from datetime import timedelta

from django.utils import timezone

from accounts.models import Guild, SchoolClass, User
from missions.models import Mission

PASSWORD = "TaynaParola123"


def make_teacher(email="uchitel@example.com"):
    return User.objects.create_user(email, PASSWORD, role=User.Role.TEACHER, first_name="Учител")


def make_student(email="uchenik@example.com", nickname="Феникс", guild_name="Builders"):
    school_class, _ = SchoolClass.objects.get_or_create(name="11А")
    return User.objects.create_user(
        email, PASSWORD, role=User.Role.STUDENT, nickname=nickname,
        school_class=school_class, guild=Guild.objects.get(name=guild_name),
    )


def make_mission(teacher, title="Мисия", xp=50, days=7, **fields):
    defaults = {
        "description": "Описание", "criteria": "Критерий",
        "guild": Guild.objects.get(name="Builders"),
        "deadline": timezone.now() + timedelta(days=days),
    }
    defaults.update(fields)
    return Mission.objects.create(title=title, xp=xp, created_by=teacher, **defaults)
