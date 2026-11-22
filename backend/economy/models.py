"""
Правилата на играта и движенията на XP и монети.

Наличностите НЕ се пазят като число в профила на ученика. Изчисляват се като
сбор от движенията, за да може всяка точка да се проследи: кой, кога, за какво (Ф12).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models

from .words import coins_text


LOGO_MAX_BYTES = 1024 * 1024


# Препоръчаните модели – ползват се, когато полето „модел“ в настройките е празно.
DEFAULT_MODELS = {
    "claude": "claude-opus-5-5",
    "gemini": "gemini-3.5-flash-lite",
    "openai": "gpt-5-mini",
}


def logo_storage():
    """Логото се показва от /school-logo/, а не от /media/ (вижте questboard/storage.py)."""
    from questboard.storage import LogoStorage

    return LogoStorage()


def validate_logo_size(file):
    if file.size > LOGO_MAX_BYTES:
        raise ValidationError("Логото трябва да е до 1 MB.")


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
    # Асистентът ползва един доставчик. Ключът за него трябва да е в .env.
    llm_provider = models.CharField(
        "доставчик", max_length=10, choices=LlmProvider.choices, default=LlmProvider.CLAUDE,
        help_text="Ключът за избрания доставчик трябва да е в .env (ANTHROPIC_API_KEY, GEMINI_API_KEY или OPENAI_API_KEY).",
    )
    llm_model = models.CharField(
        "модел", max_length=100, blank=True,
        help_text="Празно – препоръчаният модел: Claude – claude-opus-5-5, Gemini – gemini-3.5-flash-lite, "
                  "OpenAI – gpt-5-mini. След промяна запазете и натиснете „Провери асистента“.",
    )
    assistant_daily_limit = models.PositiveIntegerField("заявки към асистента на потребител на ден", default=20)

    # --- Училище ---
    # Името и логото се качват от администрацията и не са част от кода в GitHub:
    # логото е собственост на училището, а платформата може да се ползва и от други училища.
    school_name = models.CharField("име на училището", max_length=150, blank=True)
    school_logo = models.ImageField(
        "лого на училището", upload_to="branding/", blank=True, storage=logo_storage,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "webp"]), validate_logo_size],
        help_text="PNG, JPG или WebP, до 1 MB. Показва се в заглавната лента, на началната страница и на входа.",
    )
    contact_email = models.EmailField(
        "имейл за връзка", blank=True,
        help_text="Показва се в условията за ползване и политиката за поверителност.",
    )

    # --- Бонус XP от учител (без мисия) ---
    bonus_max_xp = models.PositiveIntegerField(
        "бонус XP наведнъж (най-много)", default=50,
        help_text="0 – учителите не могат да дават бонус XP.",
    )
    bonus_weekly_xp = models.PositiveIntegerField(
        "бонус XP от един учител на седмица (най-много)", default=150,
        help_text="Общо за всички ученици. Монетите от бонуса пак спазват седмичния лимит.",
    )

    undo_days = models.PositiveIntegerField(
        "учителят може да отмени награда до (дни)", default=7,
        help_text="Бонус XP, потвърдена заявка или ръчна значка. Администраторът може винаги.",
    )

    # --- Файлове към доказателствата ---
    evidence_max_files = models.PositiveIntegerField(
        "файлове към една заявка", default=3,
        help_text="Снимки (JPG, PNG, WebP) или PDF. 0 – само текст, без файлове.",
    )
    evidence_max_mb = models.PositiveIntegerField(
        "най-голям файл (MB)", default=5, validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Снимките се смаляват до 1600 px след качване, затова на диска заемат много по-малко.",
    )

    # --- Псевдоними (учениците ги сменят сами от „Профил“) ---
    nickname_change_days = models.PositiveIntegerField(
        "смяна на псевдонима веднъж на (дни)", default=30,
        help_text="0 – ученикът може да сменя псевдонима си без ограничение.",
    )
    banned_words = models.TextField(
        "забранени думи в псевдонимите", blank=True,
        default="\n".join(["admin", "админ", "администратор", "учител", "директор", "модератор"]),
        help_text="По една на ред. Псевдоним, който съдържа някоя от тях (без значение главни или малки букви), "
                  "не се приема. Не важи за вече дадените псевдоними.",
    )

    # --- Защита на входа ---
    login_max_attempts = models.PositiveIntegerField(
        "грешни пароли преди спиране", default=5, validators=[MinValueValidator(1)],
        help_text="След толкова грешни пароли за един имейл входът с него спира за известно време. "
                  "От един IP адрес се позволяват 4 пъти повече (много ученици са зад един рутер).",
    )
    login_lockout_minutes = models.PositiveIntegerField(
        "спиране за (минути)", default=15, validators=[MinValueValidator(1)],
    )

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

    def banned_word_list(self):
        return [word.strip().casefold() for word in self.banned_words.splitlines() if word.strip()]

    @property
    def model_name(self):
        """Моделът, който реално се ползва: въведеният или препоръчаният."""
        return self.llm_model.strip() or DEFAULT_MODELS[self.llm_provider]

    def assistant_model(self):
        """Какво се праща на асистента с всяка заявка: {"provider": ..., "model": ...}."""
        return {"provider": str(self.llm_provider), "model": self.model_name}

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
    is_bonus = models.BooleanField("бонус от учител", default=False)
    coins = models.PositiveIntegerField("дадени монети", default=0,
                                        help_text="Колко монети са дадени заради това XP – връщат се при отмяна.")
    # Отмяната е ново движение с минус, което сочи към отмененото. Нищо не се изтрива.
    reverses = models.OneToOneField("self", verbose_name="отменя", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="reversal")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="начислено от",
                                   on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "движение на XP"
        verbose_name_plural = "движения на XP"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student}: {self.amount:+} XP"


class CoinWeek(models.Model):
    """
    Седмична сметка за монетите на един ученик (Ф6).

    Пази колко XP е дошло през седмицата, колко е пренесено от предишната
    и колко монети са дадени. Така седмичният лимит и пренасянето на остатъка
    се изчисляват от записани числа, а не се гадаят наново.
    """

    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик",
                                on_delete=models.PROTECT, related_name="coin_weeks")
    week_start = models.DateField("седмица от")
    carry_in = models.PositiveIntegerField("пренесено XP", default=0)
    xp_earned = models.PositiveIntegerField("XP през седмицата", default=0)
    xp_used = models.PositiveIntegerField("XP, обърнато в монети", default=0)
    coins_earned = models.PositiveIntegerField("дадени монети", default=0)

    class Meta:
        verbose_name = "седмична сметка"
        verbose_name_plural = "седмични сметки за монети"
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(fields=["student", "week_start"], name="one_coin_week_per_student"),
        ]

    def __str__(self):
        return f"{self.student} – седмица от {self.week_start}"

    @property
    def xp_left(self):
        """XP, което още не е обърнато в монети."""
        return self.carry_in + self.xp_earned - self.xp_used


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
    """
    Артикул в магазина (Ф8). Два вида:
      - привилегия (Deadline Pass, Hint Token) – учителят я отбелязва като използвана;
      - за профила (титла или рамка на аватара) – само външен вид, не влияе на ученето.
    """

    class Kind(models.TextChoices):
        PRIVILEGE = "privilege", "Привилегия"
        TITLE = "title", "Титла до псевдонима"
        FRAME = "frame", "Рамка на аватара"

    class FrameStyle(models.TextChoices):
        GOLD = "gold", "Златна"
        NEON = "neon", "Неонова"
        RAINBOW = "rainbow", "Дъга"

    code = models.SlugField("код", unique=True, help_text="Ползва се в кода, напр. hint_token.")
    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.PRIVILEGE)
    name = models.CharField("име", max_length=100, help_text="При титлите това е самата титла.")
    description = models.TextField("описание", blank=True)
    price = models.PositiveIntegerField("цена в монети", validators=[MinValueValidator(1)])
    frame_style = models.CharField("вид на рамката", max_length=10, choices=FrameStyle.choices, blank=True,
                                   help_text="Само за рамки на аватара.")
    is_active = models.BooleanField("продава се", default=True)

    class Meta:
        verbose_name = "привилегия"
        verbose_name_plural = "привилегии"
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} ({coins_text(self.price)})"

    @property
    def is_cosmetic(self):
        """Титлите и рамките са само за външен вид – учителят не ги отбелязва."""
        return self.kind != self.Kind.PRIVILEGE

    def clean(self):
        if self.kind == self.Kind.FRAME and not self.frame_style:
            raise ValidationError({"frame_style": "Изберете вид на рамката."})


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
