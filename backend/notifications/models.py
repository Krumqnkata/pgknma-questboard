"""
Известия в платформата (Ф15): потвърдена или отказана заявка, ново ниво, нова значка.

Показват се със звънчето горе вдясно. Не се пращат имейли – всичко остава в сайта.
"""
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        CLAIM_APPROVED = "claim_approved", "Потвърдена заявка"
        CLAIM_REJECTED = "claim_rejected", "Отказана заявка"
        LEVEL_UP = "level_up", "Ново ниво"
        BADGE = "badge", "Нова значка"
        BONUS = "bonus", "Бонус от учител"
        UNDONE = "undone", "Отменена награда"
        TEAM = "team", "Отборна мисия"
        TEST = "test", "Тест на гилдия"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="потребител", on_delete=models.CASCADE,
                             related_name="notifications")
    kind = models.CharField("вид", max_length=20, choices=Kind.choices)
    text = models.CharField("текст", max_length=300)
    link = models.CharField("връзка", max_length=200, blank=True)
    created_at = models.DateTimeField("създадено", auto_now_add=True)
    read_at = models.DateTimeField("прочетено", null=True, blank=True)

    class Meta:
        verbose_name = "известие"
        verbose_name_plural = "известия"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return self.text

    @property
    def is_read(self):
        return self.read_at is not None
