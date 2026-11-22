"""
Значки за постижения (Ф16), напр. „Първа мисия“ или „5 мисии в една гилдия“.

Всяка значка има правило и праг. Администраторът добавя и променя значки от
администрацията, без да се пипа кодът. Ученикът получава значката сам, когато
стигне прага – проверката е при потвърдена заявка и при покупка.
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import Guild


class Badge(models.Model):
    class Rule(models.TextChoices):
        MISSIONS = "missions", "Потвърдени мисии (общо)"
        GUILD_MISSIONS = "guild_missions", "Потвърдени мисии в една гилдия"
        XP = "xp", "Натрупан опит (XP)"
        LEVEL = "level", "Достигнато ниво"
        PURCHASES = "purchases", "Покупки от магазина"
        STREAK = "streak", "Поредни седмици с изпълнена мисия"

    class Icon(models.TextChoices):
        FLAG = "flag", "Флаг"
        STAR = "star", "Звезда"
        CROWN = "crown", "Корона"
        SHIELD = "shield", "Щит"
        BOLT = "bolt", "Мълния"
        BAG = "bag", "Торба"
        FLAME = "flame", "Пламък"

    name = models.CharField("име", max_length=60, unique=True)
    description = models.CharField("описание", max_length=200)
    icon = models.CharField("икона", max_length=10, choices=Icon.choices, default=Icon.STAR)
    rule = models.CharField("правило", max_length=20, choices=Rule.choices)
    threshold = models.PositiveIntegerField("праг", validators=[MinValueValidator(1)],
                                            help_text="Напр. 5 за „5 мисии“.")
    guild = models.ForeignKey(
        Guild, verbose_name="гилдия", on_delete=models.CASCADE, null=True, blank=True,
        help_text="Само за правилото „в една гилдия“. Празно – която и да е гилдия.",
    )
    is_active = models.BooleanField("активна", default=True)
    order = models.PositiveIntegerField("ред", default=0)

    class Meta:
        verbose_name = "значка"
        verbose_name_plural = "значки"
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class StudentBadge(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик", on_delete=models.CASCADE,
                                related_name="badges")
    badge = models.ForeignKey(Badge, verbose_name="значка", on_delete=models.CASCADE, related_name="awards")
    awarded_at = models.DateTimeField("получена", auto_now_add=True)

    class Meta:
        verbose_name = "получена значка"
        verbose_name_plural = "получени значки"
        ordering = ["-awarded_at"]
        constraints = [models.UniqueConstraint(fields=["student", "badge"], name="one_badge_per_student")]

    def __str__(self):
        return f"{self.student} – {self.badge}"
