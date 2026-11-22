"""
Потребители, класове и гилдии.

Всеки потребител има една от трите роли: ученик, учител или администратор.
Правата се проверяват на сървъра по полето `role`.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class Guild(models.Model):
    """Една от четирите гилдии: Builders, Guardians, Explorers, Citizens."""

    name = models.CharField("име", max_length=50, unique=True)
    description = models.TextField("описание", blank=True)

    class Meta:
        verbose_name = "гилдия"
        verbose_name_plural = "гилдии"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    """Клас в гимназията, напр. „11А“."""

    name = models.CharField("клас", max_length=10, unique=True)

    class Meta:
        verbose_name = "клас"
        verbose_name_plural = "класове"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    """Създава потребители с имейл вместо потребителско име."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Имейлът е задължителен")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # паролата се пази само като хеш
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["role"] = User.Role.ADMIN
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Потребител на Questboard. Входът е с имейл и парола."""

    class Role(models.TextChoices):
        STUDENT = "student", "Ученик"
        TEACHER = "teacher", "Учител"
        ADMIN = "admin", "Администратор"

    # Не ползваме потребителско име – входът е с имейл.
    username = None
    email = models.EmailField("имейл", unique=True)

    role = models.CharField("роля", max_length=10, choices=Role.choices, default=Role.STUDENT)

    # Потребителите, внесени от CSV, получават временна парола и трябва да я сменят при първия вход.
    must_change_password = models.BooleanField(
        "трябва да смени паролата", default=False,
        help_text="При следващия вход потребителят ще бъде помолен да смени паролата си.",
    )

    # Полета само за ученици. В класациите се показва псевдонимът, не името.
    nickname = models.CharField(
        "псевдоним", max_length=30, unique=True, null=True, blank=True,
        help_text="Показва се в класациите вместо истинското име.",
    )
    school_class = models.ForeignKey(
        SchoolClass, verbose_name="клас", on_delete=models.PROTECT,
        null=True, blank=True, related_name="students",
    )
    guild = models.ForeignKey(
        Guild, verbose_name="гилдия", on_delete=models.PROTECT,
        null=True, blank=True, related_name="members",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "потребител"
        verbose_name_plural = "потребители"
        ordering = ["email"]

    def __str__(self):
        return self.nickname or self.get_full_name() or self.email

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    def clean(self):
        """Ученикът трябва да има псевдоним, клас и гилдия (Ф2)."""
        super().clean()
        if self.nickname == "":
            self.nickname = None  # празният псевдоним се пази като „няма“
        if self.is_student:
            missing = []
            if not self.nickname:
                missing.append("псевдоним")
            if not self.school_class_id:
                missing.append("клас")
            if not self.guild_id:
                missing.append("гилдия")
            if missing:
                raise ValidationError("Ученикът трябва да има: " + ", ".join(missing) + ".")

    def save(self, *args, **kwargs):
        # Само администраторите влизат в Django admin.
        self.is_staff = self.is_admin_role
        self.is_superuser = self.is_admin_role
        super().save(*args, **kwargs)


class LoginAttempt(models.Model):
    """Неуспешен опит за вход. Пази се, за да може входът да се спре след много грешки."""

    email = models.CharField("имейл", max_length=254, db_index=True)
    ip_address = models.GenericIPAddressField("IP адрес", null=True, blank=True, db_index=True)
    created_at = models.DateTimeField("час", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "неуспешен вход"
        verbose_name_plural = "неуспешни входове"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.ip_address or '—'})"
