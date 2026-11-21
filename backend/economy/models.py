"""
Правилата на играта и движенията на XP и монети.

Наличностите НЕ се пазят като число в профила на ученика. Изчисляват се като
сбор от движенията, за да може всяка точка да се проследи: кой, кога, за какво (Ф12).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class GameSettings(models.Model):
    """
    Настройките на играта. В базата има точно един такъв ред (pk=1).
    Променят се от Django admin без нова версия на кода (Ф13).
    """

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "понеделник"
        TUESDAY = 1, "вторник"
        WEDNESDAY = 2, "сряда"
        THURSDAY = 3, "четвъртък"
        FRIDAY = 4, "петък"
        SATURDAY = 5, "събота"
        SUNDAY = 6, "неделя"

    class LlmProvider(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Google Gemini"
        CLAUDE = "claude", "Anthropic Claude"

    # --- Правила на играта (раздел 3.1) ---
    xp_per_coin = models.PositiveIntegerField(
        "XP за 1 монета", default=50, validators=[MinValueValidator(1)],
    )
    weekly_coin_limit = models.PositiveIntegerField("седмичен лимит на монетите", default=5)
    carry_over_remainder = models.BooleanField(
        "пренасяне на остатъка", default=True,
        help_text="Пренася ли се остатъкът под курса (напр. 30 XP) за следващата седмица.",
    )
    week_start_day = models.IntegerField("седмицата започва в", choices=Weekday.choices, default=Weekday.MONDAY)
    max_xp_per_mission = models.PositiveIntegerField(
        "най-много XP за една мисия", default=100, validators=[MinValueValidator(1)],
    )

    # --- Асистент (раздел 3.2) ---
    assistant_enabled = models.BooleanField(
        "асистентът е включен", default=True,
        help_text="Ако е изключен, платформата работи, а ученикът вижда съобщение, че асистентът не е достъпен.",
    )
    llm_provider = models.CharField("доставчик на езиков модел", max_length=10,
                                    choices=LlmProvider.choices, default=LlmProvider.OPENAI)
    llm_model = models.CharField("име на модела", max_length=100, blank=True)
    assistant_daily_limit = models.PositiveIntegerField("заявки към асистента на потребител на ден", default=20)

    updated_at = models.DateTimeField("последна промяна", auto_now=True)

    class Meta:
        verbose_name = "настройки на играта"
        verbose_name_plural = "настройки на играта"

    def __str__(self):
        return "Настройки на играта"

    def save(self, *args, **kwargs):
        self.pk = 1  # винаги един и същ ред
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Настройките на играта не могат да се изтрият.")

    @classmethod
    def load(cls):
        """Връща настройките; при първо извикване ги създава със стойностите по подразбиране."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Level(models.Model):
    """Ниво на ученика според натрупания XP. XP не се харчи, затова нивото не пада."""

    number = models.PositiveIntegerField("ниво", unique=True)
    min_xp = models.PositiveIntegerField("от XP", unique=True)
    title = models.CharField("звание", max_length=50, blank=True)

    class Meta:
        verbose_name = "ниво"
        verbose_name_plural = "нива"
        ordering = ["min_xp"]

    def __str__(self):
        return f"Ниво {self.number}" + (f" – {self.title}" if self.title else "")


class XPTransaction(models.Model):
    """Едно движение на XP. Обикновено идва от потвърдена заявка."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик",
                                on_delete=models.PROTECT, related_name="xp_transactions")
    amount = models.IntegerField("XP", help_text="Отрицателно число само при корекция от администратор.")
    reason = models.CharField("основание", max_length=255)
    claim = models.ForeignKey("missions.Claim", verbose_name="заявка", on_delete=models.PROTECT,
                              null=True, blank=True, related_name="xp_transactions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="начислено от",
                                   on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "движение на XP"
        verbose_name_plural = "движения на XP"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student}: {self.amount:+} XP"


class CoinTransaction(models.Model):
    """Едно движение на монети: спечелени от XP (+) или похарчени в магазина (−)."""

    class Kind(models.TextChoices):
        EARNED = "earned", "спечелени от XP"
        SPENT = "spent", "похарчени"
        REFUND = "refund", "върнати"
        CORRECTION = "correction", "корекция"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик",
                                on_delete=models.PROTECT, related_name="coin_transactions")
    amount = models.IntegerField("монети")
    kind = models.CharField("вид", max_length=12, choices=Kind.choices)
    reason = models.CharField("основание", max_length=255)
    claim = models.ForeignKey("missions.Claim", verbose_name="заявка", on_delete=models.PROTECT,
                              null=True, blank=True, related_name="coin_transactions")
    purchase = models.ForeignKey("Purchase", verbose_name="покупка", on_delete=models.PROTECT,
                                 null=True, blank=True, related_name="coin_transactions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="от",
                                   on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "движение на монети"
        verbose_name_plural = "движения на монети"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student}: {self.amount:+} монети"


class Privilege(models.Model):
    """Привилегия в магазина, напр. Deadline Pass или Hint Token (Ф8)."""

    code = models.SlugField("код", unique=True, help_text="Ползва се в кода, напр. hint_token.")
    name = models.CharField("име", max_length=100)
    description = models.TextField("описание", blank=True)
    price = models.PositiveIntegerField("цена в монети", validators=[MinValueValidator(1)])
    is_active = models.BooleanField("продава се", default=True)

    class Meta:
        verbose_name = "привилегия"
        verbose_name_plural = "привилегии"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} ({self.price} мон.)"


class Purchase(models.Model):
    """Купена привилегия. Учителят я отбелязва като използвана (Ф9)."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик",
                                on_delete=models.PROTECT, related_name="purchases")
    privilege = models.ForeignKey(Privilege, verbose_name="привилегия", on_delete=models.PROTECT,
                                  related_name="purchases")
    # Цената се записва, защото администраторът може да я промени по-късно.
    price_paid = models.PositiveIntegerField("платена цена")
    purchased_at = models.DateTimeField("купена на", auto_now_add=True)

    used_at = models.DateTimeField("използвана на", null=True, blank=True)
    used_for_mission = models.ForeignKey("missions.Mission", verbose_name="за мисия", on_delete=models.PROTECT,
                                         null=True, blank=True, related_name="+")
    marked_used_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="отбелязана от",
                                       on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "покупка"
        verbose_name_plural = "покупки"
        ordering = ["-purchased_at"]

    def __str__(self):
        return f"{self.student}: {self.privilege.name}"

    @property
    def is_used(self):
        return self.used_at is not None
