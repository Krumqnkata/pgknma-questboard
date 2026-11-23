"""
Текстовите страници на сайта: условия за ползване и политика за поверителност.

Текстът се пише и сменя от администрацията, без промяна в кода. Форматът е
прост (вижте PAGE_FORMAT_HELP) и се превръща в HTML от филтъра page_text
в web/templatetags/questboard.py, като всичко се екранира – в текста не може
да се вмъкне HTML или JavaScript.
"""
from django.db import models
from django.urls import reverse

PAGE_FORMAT_HELP = (
    "Обикновен текст. Празен ред започва нов абзац. Ред, който започва с „## “, е заглавие, "
    "а ред с „- “ е точка от списък. „[училище]“ се заменя с името на училището, "
    "а „[имейл]“ – с имейла за връзка от „Настройки на играта“."
)


class SitePage(models.Model):
    class Slug(models.TextChoices):
        TERMS = "terms", "Условия за ползване"
        PRIVACY = "privacy", "Политика за поверителност"

    slug = models.CharField("страница", max_length=20, choices=Slug.choices, unique=True)
    title = models.CharField("заглавие", max_length=150)
    content = models.TextField("текст", help_text=PAGE_FORMAT_HELP)
    updated_at = models.DateTimeField("последна промяна", auto_now=True)

    class Meta:
        verbose_name = "страница"
        verbose_name_plural = "условия и поверителност"
        ordering = ["slug"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(self.slug)  # адресите се казват също „terms“ и „privacy“


class BotKnock(models.Model):
    """
    Колко пъти на ден някой (почти винаги бот) е търсил WordPress на сайта –
    /wp-admin/, /wp-login.php и подобни (web/views/not_wordpress.py).
    Пази се само броят за деня – без IP адреси или други данни за посетителя.
    """

    day = models.DateField("ден", unique=True)
    hits = models.PositiveIntegerField("опити", default=0)

    class Meta:
        verbose_name = "опит на бот за WordPress"
        verbose_name_plural = "опити на ботове за WordPress"
        ordering = ["-day"]

    def __str__(self):
        return f"{self.day}: {self.hits}"
