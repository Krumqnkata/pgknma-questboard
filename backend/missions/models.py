"""
Мисии и заявките на учениците за тях.

Учителят създава мисия (Ф3). Ученикът заявява изпълнение с доказателство (Ф4).
Учителят потвърждава или отказва заявката (Ф5) – XP се начислява само след
потвърждение. Логиката по начисляването е в economy, тук са само данните.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild

TEAM_LIMIT = 10  # най-многото ученици в отбор


class Mission(models.Model):
    class Kind(models.TextChoices):
        MISSION = "mission", "Мисия"
        HOMEWORK = "homework", "Домашна"

    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.MISSION)
    title = models.CharField("заглавие", max_length=200)
    description = models.TextField("описание")
    criteria = models.TextField("критерий за изпълнение")
    guild = models.ForeignKey(Guild, verbose_name="гилдия", on_delete=models.PROTECT, related_name="missions",
                              null=True, blank=True, help_text="Задължителна за мисия; домашната е без гилдия.")
    # --- Само за домашна ---
    subject = models.CharField("предмет", max_length=60, blank=True)
    school_classes = models.ManyToManyField(
        "accounts.SchoolClass", verbose_name="класове", blank=True, related_name="homework",
        help_text="Домашната се вижда само от тези класове.",
    )
    xp = models.PositiveIntegerField("XP")
    deadline = models.DateTimeField("краен срок")
    hints_allowed = models.BooleanField(
        "разрешени подсказки", default=True,
        help_text="Може ли ученикът да ползва Hint Token за тази мисия.",
    )
    is_active = models.BooleanField("активна", default=True)

    # --- Отборна мисия ---
    is_group = models.BooleanField(
        "отборна мисия", default=False,
        help_text="Един ученик (капитанът) подава заявката и посочва съотборниците си. "
                  "При потвърждение всеки от отбора получава пълната награда.",
    )
    team_min = models.PositiveSmallIntegerField("най-малко ученици в отбор", default=2)
    team_max = models.PositiveSmallIntegerField("най-много ученици в отбор", default=4)

    # --- Награди само за тази мисия (освен XP) ---
    reward_badge = models.ForeignKey(
        "badges.Badge", verbose_name="значка за изпълнение", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="missions",
        help_text="Значка с правило „Дава се от мисия“.",
    )
    reward_item = models.ForeignKey(
        "economy.Privilege", verbose_name="предмет за изпълнение", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="missions",
        help_text="Предмет, който се печели само от мисия, или награда от външен контрибутор.",
    )

    # --- Кой проверява ---
    reviewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name="заместници при проверката", blank=True,
        related_name="missions_to_review", limit_choices_to={"role": "teacher", "is_active": True},
        help_text="Учители, които също могат да потвърждават и отказват заявките. "
                  "Ако не изберете никого, проверявате само вие.",
    )

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

    @property
    def is_homework(self):
        return self.kind == self.Kind.HOMEWORK

    @property
    def source(self):
        """Откъде е: гилдията на мисията или предметът на домашната."""
        return self.subject if self.is_homework else str(self.guild or "")

    def is_visible_to(self, student):
        """Домашната е само за класовете си; мисиите са за всички."""
        return not self.is_homework or self.school_classes.filter(pk=student.school_class_id).exists()

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

        rules = GameSettings.load()
        max_xp = rules.max_xp_per_homework if self.is_homework else rules.max_xp_per_mission
        if self.xp is not None and self.xp > max_xp:
            what = "домашна" if self.is_homework else "мисия"
            errors["xp"] = f"Най-много {max_xp} XP за една {what} (настройва се от администратора)."
        if self.is_homework and not self.subject.strip():
            errors["subject"] = "Напишете предмета."
        if not self.is_homework and not self.guild_id:
            errors["guild"] = "Изберете гилдия."
        if self.xp == 0:
            errors["xp"] = "Мисията трябва да носи поне 1 XP."

        # Нова мисия не може да е с изтекъл срок. При редакция на стара мисия е позволено.
        if self._state.adding and self.deadline and self.deadline <= timezone.now():
            errors["deadline"] = "Крайният срок трябва да е в бъдещето."

        if self.is_group:
            if not self.team_min or self.team_min < 2:
                errors["team_min"] = "В отбор има поне 2 ученици."
            elif not self.team_max or self.team_max < self.team_min:
                errors["team_max"] = "Най-големият отбор не може да е по-малък от най-малкия."
            elif self.team_max > TEAM_LIMIT:
                errors["team_max"] = f"Най-много {TEAM_LIMIT} ученици в отбор."

        if errors:
            raise ValidationError(errors)

    def can_be_reviewed_by(self, user):
        """Авторът на мисията, избраните от него заместници и администраторът."""
        if user.is_admin_role:
            return True
        return user.is_teacher and (self.created_by_id == user.pk or self.reviewers.filter(pk=user.pk).exists())


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
    # Отборна мисия: всеки от отбора има своя заявка, а тези на съотборниците сочат към
    # заявката на капитана. Така XP, значките, серията и правилото „една заявка на мисия“
    # важат за всеки поотделно. Решението се взима веднъж – по заявката на капитана.
    captain = models.ForeignKey(
        "self", verbose_name="заявка на капитана", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="team",
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


def _random_path(folder, instance):
    """Случайно име: никой не може да познае адреса на чужд файл, а и името не издава нищо."""
    extension = "jpg" if instance.kind == FileKind.IMAGE else instance.kind
    return f"{folder}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{extension}"


def evidence_path(instance, filename):
    return _random_path("evidence", instance)


def mission_file_path(instance, filename):
    return _random_path("mission_files", instance)


class FileKind(models.TextChoices):
    """Какво може да се качи. Проверява се по съдържанието на файла (missions/evidence.py)."""

    IMAGE = "image", "Снимка"
    PDF = "pdf", "PDF документ"
    DOCX = "docx", "Word документ"
    XLSX = "xlsx", "Excel таблица"
    PPTX = "pptx", "PowerPoint презентация"


class EvidenceFile(models.Model):
    """
    Снимка или документ към заявка. Файловете са в media/evidence/ и НЕ са публични:
    показват се само през web/views/evidence.py, след проверка кой ги гледа
    (ученикът, учителят на мисията или администраторът).
    """

    Kind = FileKind

    claim = models.ForeignKey(Claim, verbose_name="заявка", on_delete=models.CASCADE, related_name="files")
    file = models.FileField("файл", upload_to=evidence_path)
    kind = models.CharField("вид", max_length=10, choices=Kind.choices)
    original_name = models.CharField("име при качване", max_length=150)
    size = models.PositiveIntegerField("размер (байта)")
    uploaded_at = models.DateTimeField("качен на", auto_now_add=True)

    class Meta:
        verbose_name = "файл към доказателство"
        verbose_name_plural = "файлове към доказателства"
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return self.original_name

    def get_absolute_url(self):
        return reverse("evidence_file", args=[self.pk])

    @property
    def is_image(self):
        return self.kind == self.Kind.IMAGE


class MissionFile(models.Model):
    """
    Файл от учителя към мисията: указания, образец, плакат. Не е публичен –
    показва се през web/views/evidence.py на всеки, който вижда самата мисия.
    """

    mission = models.ForeignKey(Mission, verbose_name="мисия", on_delete=models.CASCADE, related_name="files")
    file = models.FileField("файл", upload_to=mission_file_path)
    kind = models.CharField("вид", max_length=10, choices=FileKind.choices)
    original_name = models.CharField("име при качване", max_length=150)
    size = models.PositiveIntegerField("размер (байта)")
    uploaded_at = models.DateTimeField("качен на", auto_now_add=True)

    class Meta:
        verbose_name = "файл към мисия"
        verbose_name_plural = "файлове към мисии"
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return self.original_name

    def get_absolute_url(self):
        return reverse("mission_file", args=[self.pk])

    @property
    def is_image(self):
        return self.kind == FileKind.IMAGE
