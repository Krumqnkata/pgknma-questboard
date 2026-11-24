"""
Журнал на ползването на асистента (раздел 3.2): кой, кога, по коя мисия.

Не пазим текста на разговорите (справките) – какво вижда учителят от тях е още
за решаване (въпрос 8 от плана). Пазим само дадените подсказки, защото ученикът
ги е платил и трябва да може да ги прочете пак.
"""
from django.conf import settings
from django.db import models


class AssistantLog(models.Model):
    class Kind(models.TextChoices):
        HINT = "hint", "подсказка"
        MISSION_DRAFT = "mission_draft", "чернова на мисия"
        QUERY = "query", "справка"
        DIAGNOSE = "diagnose", "проверка на системата"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="потребител", on_delete=models.PROTECT,
                             related_name="assistant_logs")
    kind = models.CharField("вид", max_length=20, choices=Kind.choices)
    mission = models.ForeignKey("missions.Mission", verbose_name="мисия", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="+")
    success = models.BooleanField("успешно", default=False)
    provider = models.CharField("отговорил модел", max_length=20, blank=True)
    error = models.CharField("грешка", max_length=255, blank=True)
    duration_ms = models.PositiveIntegerField("време за отговор (мс)", null=True, blank=True)
    created_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "ползване на асистента"
        verbose_name_plural = "журнал на асистента"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} – {self.get_kind_display()}"


class Hint(models.Model):
    """Подсказка, получена срещу Hint Token (Ф10). Пази се, за да може ученикът да я прочете пак."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик", on_delete=models.PROTECT,
                                related_name="hints")
    mission = models.ForeignKey("missions.Mission", verbose_name="мисия", on_delete=models.PROTECT,
                                related_name="hints")
    purchase = models.OneToOneField("economy.Purchase", verbose_name="използван Hint Token",
                                    on_delete=models.PROTECT, related_name="hint")
    text = models.TextField("подсказка")
    created_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "подсказка"
        verbose_name_plural = "подсказки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} – {self.mission}"
