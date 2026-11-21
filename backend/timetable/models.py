"""
Седмичното разписание на гимназията: кой клас, кой учител, кой предмет, в кой кабинет.

От тези данни се отговаря на справките Ф17 (учители), Ф18 (класове) и
Ф22 (свободни кабинети). Данните се внасят от CSV файл (виж importer.py).
"""
from django.conf import settings
from django.db import models

from accounts.models import SchoolClass


class Room(models.Model):
    name = models.CharField("кабинет", max_length=30, unique=True)

    class Meta:
        verbose_name = "кабинет"
        verbose_name_plural = "кабинети"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField("предмет", max_length=100, unique=True)

    class Meta:
        verbose_name = "предмет"
        verbose_name_plural = "предмети"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Lesson(models.Model):
    """Един учебен час от седмичното разписание."""

    class Day(models.IntegerChoices):
        MONDAY = 0, "понеделник"
        TUESDAY = 1, "вторник"
        WEDNESDAY = 2, "сряда"
        THURSDAY = 3, "четвъртък"
        FRIDAY = 4, "петък"

    day = models.IntegerField("ден", choices=Day.choices)
    period = models.PositiveSmallIntegerField("пореден час")
    start_time = models.TimeField("начало")
    end_time = models.TimeField("край")

    school_class = models.ForeignKey(SchoolClass, verbose_name="клас", on_delete=models.CASCADE,
                                     related_name="lessons")
    subject = models.ForeignKey(Subject, verbose_name="предмет", on_delete=models.PROTECT, related_name="lessons")
    # Името е от разписанието. Не всеки учител има акаунт в Questboard,
    # затова връзката към акаунт е по желание и се попълва при съвпадение на името.
    teacher_name = models.CharField("учител", max_length=100)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="акаунт на учителя", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="lessons",
                                limit_choices_to={"role": "teacher"})
    room = models.ForeignKey(Room, verbose_name="кабинет", on_delete=models.PROTECT,
                             null=True, blank=True, related_name="lessons")

    # Нарочно няма ограничение „един клас – един час по едно и също време“:
    # при часове по групи (напр. езици) един клас има два часа едновременно.

    class Meta:
        verbose_name = "учебен час"
        verbose_name_plural = "разписание"
        ordering = ["day", "period", "school_class__name"]
        indexes = [models.Index(fields=["day", "period"]), models.Index(fields=["teacher_name"])]

    def __str__(self):
        return f"{self.get_day_display()}, {self.period} час – {self.school_class}: {self.subject}"
