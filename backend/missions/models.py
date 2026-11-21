"""
Мисии и заявките на учениците за тях.

Учителят създава мисия (Ф3). Ученикът заявява изпълнение с доказателство (Ф4).
Учителят потвърждава или отказва заявката (Ф5) – XP се начислява само след
потвърждение. Логиката по начисляването е в economy, тук са само данните.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import Guild


class Mission(models.Model):
    title = models.CharField("заглавие", max_length=200)
    description = models.TextField("описание")
    criteria = models.TextField("критерий за изпълнение")
    guild = models.ForeignKey(Guild, verbose_name="гилдия", on_delete=models.PROTECT, related_name="missions")
    xp = models.PositiveIntegerField("XP")
    deadline = models.DateTimeField("краен срок")
    hints_allowed = models.BooleanField(
        "разрешени подсказки", default=True,
        help_text="Може ли ученикът да ползва Hint Token за тази мисия.",
    )
    is_active = models.BooleanField("активна", default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="създадена от",
        on_delete=models.PROTECT, related_name="created_missions",
    )
    created_at = models.DateTimeField("създадена на", auto_now_add=True)
    updated_at = models.DateTimeField("променена на", auto_now=True)

    class Meta:
        verbose_name = "мисия"
        verbose_name_plural = "мисии"
        ordering = ["deadline"]

    def __str__(self):
        return self.title

    def is_open(self):
        """Може ли още да се заявява изпълнение."""
        return self.is_active and timezone.now() <= self.deadline

    def clean(self):
        """
        Правилата за мисия. Django ги проверява във формите и в admin,
        а API-то ги вика ръчно (виж api/serializers.py).
        """
        from economy.models import GameSettings  # тук, за да няма кръгов импорт

        super().clean()
        errors = {}

        max_xp = GameSettings.load().max_xp_per_mission
        if self.xp is not None and self.xp > max_xp:
            errors["xp"] = f"Най-много {max_xp} XP за една мисия (настройва се от администратора)."
        if self.xp == 0:
            errors["xp"] = "Мисията трябва да носи поне 1 XP."

        # Нова мисия не може да е с изтекъл срок. При редакция на стара мисия е позволено.
        if self._state.adding and self.deadline and self.deadline <= timezone.now():
            errors["deadline"] = "Крайният срок трябва да е в бъдещето."

        if errors:
            raise ValidationError(errors)


class Claim(models.Model):
    """Заявка на ученик, че е изпълнил мисия."""

    class Status(models.TextChoices):
        PENDING = "pending", "Чака проверка"
        APPROVED = "approved", "Потвърдена"
        REJECTED = "rejected", "Отказана"

    mission = models.ForeignKey(Mission, verbose_name="мисия", on_delete=models.PROTECT, related_name="claims")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ученик",
        on_delete=models.PROTECT, related_name="claims",
    )
    evidence = models.TextField("доказателство", help_text="Кратък текст или връзка.")
    status = models.CharField("състояние", max_length=10, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField("подадена на", auto_now_add=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="проверена от",
        on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_claims",
    )
    reviewed_at = models.DateTimeField("проверена на", null=True, blank=True)
    review_comment = models.TextField("коментар на учителя", blank=True)

    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "заявки"
        ordering = ["-submitted_at"]
        constraints = [
            # Граничен случай от 3.1: ученик заявява една и съща мисия два пъти.
            # Базата сама не позволява втора заявка; отказана заявка се подава отново,
            # като се промени същият ред.
            models.UniqueConstraint(fields=["mission", "student"], name="one_claim_per_student_per_mission"),
        ]

    def __str__(self):
        return f"{self.student} → {self.mission}"
