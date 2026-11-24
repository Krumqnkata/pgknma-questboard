"""
Изтрива всичко от базата и зарежда демо данните наново (seed_demo и seed_activity).

    python manage.py reset_demo

Трият се ВСИЧКИ акаунти (и администраторите), мисии, заявки, файлове, тестове, покупки,
известия и журнали. Остават настройките: правила на играта, училище и лого, нива, гилдии,
началните значки и предмети, текстовете на страниците и разписанието.

Няма връщане назад: първо направете копие на базата и на папката media.
"""
import os
from pathlib import Path

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import LoginAttempt, NicknameChange, SchoolClass, User
from assistant_bridge.models import AssistantLog, Hint
from badges.models import Badge, StudentBadge
from economy.models import CoinTransaction, CoinWeek, Privilege, Purchase, Sponsor, XPTransaction
from missions.models import Claim, EvidenceFile, Mission, MissionFile
from notifications.models import Notification
from quizzes.models import Attempt, AttemptAnswer, GuildTest, Question, TestSession
from web.models import BotKnock

CONFIRM = "ИЗТРИЙ"

# Редът е важен: първо това, което сочи към останалото.
CONTENT = [Notification, AssistantLog, Hint, AttemptAnswer, Attempt, TestSession, Question, GuildTest, StudentBadge,
           CoinTransaction, XPTransaction, CoinWeek, Purchase, EvidenceFile, MissionFile, Claim, Mission,
           NicknameChange, LoginAttempt, BotKnock, LogEntry, Session]

# Началните значки и предмети (от миграциите) остават, добавените после се трият.
BADGES = ["Първа мисия", "Пет мисии", "Верен на гилдията", "Десет мисии", "Майстор", "Пръв в магазина",
          "Три седмици подред", "Пет седмици подред", "Десет седмици подред", "Звезда на седмицата", "Отборен играч",
          "Златна идея", "Екипен дух", "Първооткривател"]
ITEMS = ["deadline_pass", "hint_token", "title_lightning", "title_strategist", "title_legend", "title_discoverer",
         "frame_gold", "frame_neon", "frame_rainbow"]
FOLDERS = {"evidence": EvidenceFile, "mission_files": MissionFile}


class Command(BaseCommand):
    help = "Изтрива всичко и зарежда демо данните наново. Няма връщане назад."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="без въпрос")

    def handle(self, *args, **options):
        if len(os.getenv("DEMO_PASSWORD", "")) < 8:
            raise CommandError("Сложете DEMO_PASSWORD в .env (поне 8 символа).")
        database = settings.DATABASES["default"]
        self.stdout.write(self.style.WARNING(f"От базата {database['NAME']} ще се изтрият:"))
        for model in [User, Mission, Claim, EvidenceFile, GuildTest, Purchase, XPTransaction, Notification]:
            self.stdout.write(f"  {model._meta.verbose_name_plural}: {model.objects.count()}")
        if not options["yes"]:
            answer = input(f"Имате ли копие на базата? Напишете {CONFIRM}, за да продължите: ")
            if answer.strip() != CONFIRM:
                raise CommandError("Нищо не е изтрито.")

        with transaction.atomic():  # ако нещо се счупи, базата остава каквато е била
            self.wipe()
            call_command("seed_demo", stdout=self.stdout)
            call_command("seed_activity", stdout=self.stdout)
        cache.clear()
        self.remove_old_files()

    def wipe(self):
        User.objects.update(shown_title=None, shown_frame=None)
        XPTransaction.objects.update(reverses=None)
        Claim.objects.update(captain=None)
        for model in CONTENT:
            model.objects.all().delete()
        User.objects.all().delete()
        Privilege.objects.exclude(code__in=ITEMS).delete()
        Badge.objects.exclude(name__in=BADGES).delete()
        for sponsor in Sponsor.objects.exclude(logo=""):
            transaction.on_commit(lambda logo=sponsor.logo: logo.delete(save=False))
        Sponsor.objects.all().delete()
        SchoolClass.objects.filter(lessons__isnull=True).delete()  # класовете от разписанието остават

    def remove_old_files(self):
        """Файлове, към които вече нищо в базата не сочи."""
        root = Path(settings.MEDIA_ROOT)
        for folder, model in FOLDERS.items():
            used = set(model.objects.values_list("file", flat=True))
            for path in (root / folder).rglob("*.*"):
                if path.is_file() and path.relative_to(root).as_posix() not in used:
                    path.unlink()
