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
