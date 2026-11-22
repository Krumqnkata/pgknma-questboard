"""
Как се сервират CSS и JavaScript, когато DEBUG=False.

В публикуваната версия (start.py --production) файловете се подготвят с
collectstatic: компресират се и получават уникални имена (напр. style.3ca7f6.css),
за да може браузърът да ги пази дълго.

Ако някой изключи DEBUG, без да ги е подготвил (например при локална проба),
стандартното хранилище на Django хвърля грешка и всяка страница дава грешка 500.
Това хранилище в такъв случай просто връща обикновения адрес (style.css),
а WhiteNoise намира файла направо в папката static/.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False  # липсващ файл в списъка не е фатална грешка

    def url(self, name, force=False):
        try:
            return super().url(name, force)
        except ValueError:
            # Файлът не е подготвен с collectstatic – адрес без уникалното име.
            return f"{self.base_url}{name}"
