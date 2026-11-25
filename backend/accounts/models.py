"""
Потребители, класове и гилдии.

Всеки потребител има една от трите роли: ученик, учител или администратор.
Правата се проверяват на сървъра по полето `role`.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


MAX_GUILDS = 2  # в най-много толкова гилдии е един ученик


class Guild(models.Model):
    """
    Гилдия по интереси: Помощници, Артисти, Техничари, Спортисти, Организатори.
    `code` е на латиница и не се сменя – по него сайтът избира цвета и иконата.
    """

    class Code(models.TextChoices):
        HELPERS = "helpers", "Помощници (син, щит)"
        ARTISTS = "artists", "Артисти (розов, четка)"
        TECHIES = "techies", "Техничари (оранжев, гаечен ключ)"
        ATHLETES = "athletes", "Спортисти (червен, мълния)"
        ORGANIZERS = "organizers", "Организатори (лилав, хора)"

    name = models.CharField("име", max_length=50, unique=True)
    code = models.CharField("цвят и икона", max_length=12, choices=Code.choices, default=Code.HELPERS,
                            help_text="Определя цвета и иконата на гилдията в сайта.")
    description = models.TextField("описание", blank=True)
    # Само за връзка и информация: мисии и тестове може да прави всеки учител.
    leaders = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name="отговорници", blank=True, related_name="led_guilds",
        limit_choices_to={"role": "teacher", "is_active": True},
        help_text="Учителите, към които учениците се обръщат за гилдията. Един учител може да отговаря за няколко.",
    )

    class Meta:
        verbose_name = "гилдия"
        verbose_name_plural = "гилдии"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def active_leaders(self):
        return [user for user in self.leaders.all() if user.is_active and user.is_teacher]


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
    # Най-много две гилдии. От основната идват видът на сайта и мястото на XP в класацията (guilds.py).
    guild = models.ForeignKey(
        Guild, verbose_name="основна гилдия", on_delete=models.PROTECT,
        null=True, blank=True, related_name="members",
    )
    second_guild = models.ForeignKey(
        Guild, verbose_name="втора гилдия", on_delete=models.PROTECT,
        null=True, blank=True, related_name="second_members",
    )
    main_guild_changed_at = models.DateTimeField("сменил основната гилдия на", null=True, blank=True, editable=False)

    # Външен вид в класациите: аватарът се рисува от това число (web/avatars.py),
    # а титлата и рамката се купуват в магазина и ученикът избира коя да се вижда.
    avatar_seed = models.PositiveIntegerField("шарка на аватара", default=0)
    shown_title = models.ForeignKey(
        "economy.Privilege", verbose_name="показвана титла", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    shown_frame = models.ForeignKey(
        "economy.Privilege", verbose_name="показвана рамка", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
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

    @property
    def guilds(self):
        """Гилдиите на ученика, основната е първа."""
        return [guild for guild in (self.guild, self.second_guild) if guild]

    @property
    def guild_ids(self):
        return [pk for pk in (self.guild_id, self.second_guild_id) if pk]

    def clean(self):
        """Ученикът трябва да има псевдоним и клас (Ф2). Гилдията може да се избере и после, с входен тест."""
        super().clean()
        if self.second_guild_id and not self.guild_id:
            self.guild, self.second_guild = self.second_guild, None
        if self.second_guild_id and self.second_guild_id == self.guild_id:
            raise ValidationError({"second_guild": "Втората гилдия трябва да е различна от основната."})
        if self.nickname == "":
            self.nickname = None  # празният псевдоним се пази като „няма“
        if self.is_student:
            missing = []
            if not self.nickname:
                missing.append("псевдоним")
            if not self.school_class_id:
                missing.append("клас")
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


class NicknameChange(models.Model):
    """
    История на псевдонимите. Пази се, за да може администраторът да види кой
    кой е бил и да върне стар псевдоним, ако новият е неподходящ.
    """

    student = models.ForeignKey(User, verbose_name="ученик", on_delete=models.CASCADE, related_name="nickname_changes")
    old = models.CharField("стар псевдоним", max_length=30, blank=True)
    new = models.CharField("нов псевдоним", max_length=30)
    changed_by = models.ForeignKey(User, verbose_name="сменен от", on_delete=models.SET_NULL, null=True,
                                   related_name="+")
    changed_at = models.DateTimeField("кога", auto_now_add=True)

    class Meta:
        verbose_name = "смяна на псевдоним"
        verbose_name_plural = "смени на псевдоними"
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.old or '—'} → {self.new}"
