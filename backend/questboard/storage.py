"""
Как се сервират CSS и JavaScript, когато DEBUG=False.

В публикуваната версия (start.py --production) файловете се подготвят с
collectstatic: компресират се и получават уникални имена (напр. style.3ca7f6.css),
за да може браузърът да ги пази дълго.

Ако някой изключи DEBUG, без да ги е подготвил (например при локална проба),
стандартното хранилище на Django хвърля грешка и всяка страница дава грешка 500.
Това хранилище в такъв случай просто връща обикновения адрес (style.css),
а WhiteNoise намира файла направо в папката static/.

Тук са и хранилищата за логото на училището и на спонсорите.
"""
from urllib.parse import quote

from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False  # липсващ файл в списъка не е фатална грешка

    def url(self, name, force=False):
        try:
            return super().url(name, force)
        except ValueError:
            # Файлът не е подготвен с collectstatic – адрес без уникалното име.
            return f"{self.base_url}{name}"


class LogoStorage(FileSystemStorage):
    """
    Логото на училището се пази в media/branding/, но се показва от адреса
    /school-logo/ (web/views/branding.py). Така прегледът в администрацията
    работи и в публикуваната версия, където папката media/ не се сервира.
    """

    def url(self, name):
        return f"{reverse('school_logo')}?v={quote(name or '')}"


class SponsorLogoStorage(FileSystemStorage):
    """Логата на спонсорите (media/sponsors/) се показват от /sponsor-logo/<име> (web/views/branding.py)."""

    def url(self, name):
        return reverse("sponsor_logo", args=[(name or "").rsplit("/", 1)[-1]])
