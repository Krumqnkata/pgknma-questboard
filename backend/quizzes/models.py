"""
Тестовете на гилдиите.

  - Входен тест: който го мине, влиза в гилдията.
  - Месечен тест: само за членовете, дава XP, ако се мине навреме.

Тест се решава само пред учител: учителят пуска сесия с код, който важи няколко
минути. Въпросите идват един по един от сървъра, разбъркани, с време за всеки.
Правилата са в quizzes/services.py – тук са само данните.
"""
import random
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import Guild


class GuildTest(models.Model):
    class Kind(models.TextChoices):
        ENTRY = "entry", "Входен"
        MONTHLY = "monthly", "Месечен"

    guild = models.ForeignKey(Guild, verbose_name="гилдия", on_delete=models.PROTECT, related_name="tests")
    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.ENTRY)
    title = models.CharField("заглавие", max_length=120)
    description = models.TextField("за какво е", blank=True, help_text="Ученикът го вижда преди теста.")
    questions_count = models.PositiveSmallIntegerField(
        "въпроси в един опит", default=10, validators=[MinValueValidator(3), MaxValueValidator(50)],
        help_text="Избират се на случаен принцип от одобрените.",
    )
    seconds = models.PositiveSmallIntegerField(
        "секунди за въпрос", default=12, validators=[MinValueValidator(5), MaxValueValidator(600)],
        help_text="За кратък въпрос 10–15 са достатъчни да се прочете и да не остане време за търсене. "
                  "При практическа задача може да се зададе друго време за самата задача.",
    )
    pass_percent = models.PositiveSmallIntegerField(
        "минава се с (%)", default=80, validators=[MinValueValidator(1), MaxValueValidator(100)])
    xp = models.PositiveIntegerField("XP при успех", default=0, help_text="Само за месечен тест.")
    retry_days = models.PositiveSmallIntegerField(
        "нов опит след (дни)", default=7, help_text="Само за входен тест. Месечният е веднъж на месец.")
    is_active = models.BooleanField("активен", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="създаден от", on_delete=models.PROTECT,
                                   related_name="created_tests")
    created_at = models.DateTimeField("създаден на", auto_now_add=True)

    class Meta:
        verbose_name = "тест на гилдия"
        verbose_name_plural = "тестове на гилдиите"
        ordering = ["guild__name", "kind", "title"]

    def __str__(self):
        return f"{self.title} ({self.guild})"

    @property
    def is_entry(self):
        return self.kind == self.Kind.ENTRY

    def approved_questions(self):
        return self.questions.filter(is_approved=True)

    def clean(self):
        from economy.models import GameSettings

        super().clean()
        if self.kind == self.Kind.MONTHLY:
            limit = GameSettings.load().max_xp_per_mission
            if not 1 <= (self.xp or 0) <= limit:
                raise ValidationError({"xp": f"Месечният тест дава от 1 до {limit} XP."})
        else:
            self.xp = 0


class Question(models.Model):
    class Kind(models.TextChoices):
        CHOICE = "choice", "Избор на един отговор"
        ORDER = "order", "Подреди стъпките"
        TEXT = "text", "Напиши отговор или команда"

    test = models.ForeignKey(GuildTest, verbose_name="тест", on_delete=models.CASCADE, related_name="questions")
    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.CHOICE)
    text = models.TextField("въпрос или задача", max_length=600)
    answers = models.TextField(
        "отговори", max_length=1500,
        help_text="По един на ред. Избор: сложете * пред верния. Подреждане: стъпките във верния ред. "
                  "Писмен: всички приемани отговори.",
    )
    seconds = models.PositiveSmallIntegerField(
        "секунди за този въпрос", null=True, blank=True, validators=[MinValueValidator(5), MaxValueValidator(600)],
        help_text="Празно – колкото е за целия тест.",
    )
    is_approved = models.BooleanField("одобрен", default=True, help_text="Черновите от асистента чакат одобрение.")
    created_at = models.DateTimeField("създаден на", auto_now_add=True)

    class Meta:
        verbose_name = "въпрос"
        verbose_name_plural = "въпроси"
        ordering = ["id"]

    def __str__(self):
        return self.text[:80]

    @property
    def lines(self):
        return [line.strip() for line in self.answers.splitlines() if line.strip()]

    @property
    def options(self):
        """Това, което ученикът вижда (без знака за верен отговор)."""
        return [] if self.kind == self.Kind.TEXT else [line.removeprefix("*").strip() if self.kind == self.Kind.CHOICE
                                                       else line for line in self.lines]

    @property
    def time_limit(self):
        return self.seconds or self.test.seconds

    def clean(self):
        super().clean()
        lines = self.lines
        if self.kind == self.Kind.CHOICE:
            if not 2 <= len(lines) <= 6:
                raise ValidationError({"answers": "Дайте от 2 до 6 отговора, по един на ред."})
            if sum(line.startswith("*") for line in lines) != 1:
                raise ValidationError({"answers": "Сложете * пред точно един верен отговор."})
            if len(set(self.options)) != len(self.options):
                raise ValidationError({"answers": "Два отговора са еднакви."})
        elif self.kind == self.Kind.ORDER:
            if not 3 <= len(lines) <= 7 or len(set(lines)) != len(lines):
                raise ValidationError({"answers": "Дайте от 3 до 7 различни стъпки във верния ред."})
        elif not lines:
            raise ValidationError({"answers": "Напишете поне един приеман отговор."})

    # ---------- Показване и проверка ----------

    def shuffled(self, secret):
        """
        Отговорите, разбъркани за този опит: [(номер за показване, текст)]. Номерът е мястото в
        разбъркания списък и не издава верния отговор; редът се възстановява от тайната на опита.
        """
        return list(enumerate(self.options[i] for i in self._order(secret)))

    def _order(self, secret):
        order = list(range(len(self.options)))
        random.Random(f"{secret}:{self.pk}").shuffle(order)
        return order

    def is_correct(self, value, secret):
        value = str(value or "").strip()
        if self.kind == self.Kind.TEXT:
            return normalize(value) in {normalize(line) for line in self.lines} if value else False
        order = self._order(secret)
        try:
            picked = [order[int(item)] for item in value.split(",")]
        except (ValueError, IndexError):
            return False
        if self.kind == self.Kind.CHOICE:
            return len(picked) == 1 and self.lines[picked[0]].startswith("*")
        return picked == list(range(len(self.options)))


def normalize(text):
    """„ Print( 1 ) ;“ и „print(1)“ са еднакви: без значение са главните букви, интервалите и крайната точка."""
    return re.sub(r"\s+", "", text).casefold().rstrip(".;")


class TestSession(models.Model):
    """Учителят е пуснал теста за няколко минути. Без кода опит не започва."""

    test = models.ForeignKey(GuildTest, verbose_name="тест", on_delete=models.PROTECT, related_name="sessions")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="учител", on_delete=models.PROTECT,
                                related_name="test_sessions")
    code = models.CharField("код", max_length=6, db_index=True)
    opened_at = models.DateTimeField("пусната на", auto_now_add=True)
    expires_at = models.DateTimeField("започване до")

    class Meta:
        verbose_name = "сесия на тест"
        verbose_name_plural = "сесии на тестовете"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"{self.test} – {timezone.localtime(self.opened_at):%d.%m %H:%M}"

    @property
    def is_open(self):
        return timezone.now() < self.expires_at


class Attempt(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "В момента"
        PASSED = "passed", "Минат"
        FAILED = "failed", "Неуспешен"
        VOID = "void", "Анулиран"

    test = models.ForeignKey(GuildTest, verbose_name="тест", on_delete=models.PROTECT, related_name="attempts")
    session = models.ForeignKey(TestSession, verbose_name="сесия", on_delete=models.PROTECT, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="ученик", on_delete=models.PROTECT,
                                related_name="test_attempts")
    status = models.CharField("състояние", max_length=10, choices=Status.choices, default=Status.RUNNING)
    secret = models.CharField(max_length=32, editable=False)          # за разбъркването
    question_ids = models.JSONField("въпроси", default=list)
    position = models.PositiveSmallIntegerField("стигнал до въпрос", default=0)
    question_started_at = models.DateTimeField("въпросът е показан в", null=True, blank=True)
    correct = models.PositiveSmallIntegerField("верни", default=0)
    left_page = models.PositiveSmallIntegerField("излизал от страницата (пъти)", default=0)
    started_at = models.DateTimeField("започнат", auto_now_add=True)
    deadline = models.DateTimeField("най-късно до")
    finished_at = models.DateTimeField("завършен", null=True, blank=True)
    xp_entry = models.OneToOneField("economy.XPTransaction", verbose_name="начислен XP", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="test_attempt")
    void_reason = models.CharField("защо е анулиран", max_length=200, blank=True)

    class Meta:
        verbose_name = "опит за тест"
        verbose_name_plural = "опити за тестове"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.student} – {self.test}"

    @property
    def total(self):
        return len(self.question_ids)

    @property
    def percent(self):
        return round(self.correct * 100 / self.total) if self.total else 0


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, verbose_name="опит", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, verbose_name="въпрос", on_delete=models.SET_NULL, null=True)
    value = models.CharField("отговор", max_length=300, blank=True)
    is_correct = models.BooleanField("верен", default=False)
    seconds = models.FloatField("секунди", default=0)

    class Meta:
        verbose_name = "отговор"
        verbose_name_plural = "отговори"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question")]
