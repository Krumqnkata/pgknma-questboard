"""
Внася разписанието от CSV файл от командния ред:

    python manage.py import_timetable път/до/файла.csv

Същото може да се направи и от администрацията (Разписание → Внеси от CSV).
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from timetable.importer import import_timetable


class Command(BaseCommand):
    help = "Заменя разписанието с това от CSV файл."

    def add_arguments(self, parser):
        parser.add_argument("file", help="CSV файл в UTF-8")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Няма такъв файл: {path}")
        result = import_timetable(path.read_text(encoding="utf-8-sig"))
        if not result.ok:
            raise CommandError("Разписанието НЕ е внесено:\n" + "\n".join(result.errors))
        self.stdout.write(self.style.SUCCESS(f"Внесени учебни часа: {result.created}"))
