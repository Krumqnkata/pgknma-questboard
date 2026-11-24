"""
Добавя осем седмици живот към демо данните: заявки с истински снимки, проверки, отбори,
домашни, тестове, бонуси, покупки, значки и известия.

    python manage.py seed_demo       # първо основните демо данни
    python manage.py seed_activity

Всичко минава през правилата на играта, в своя момент от миналото (accounts/demo/story.py).
Командата отказва да работи, ако в базата има хора извън демо домейна или вече има заявки.
За ново начало е reset_demo.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.demo.content import DOMAIN
from accounts.demo.story import Story
from accounts.models import User
from economy.models import XPTransaction
from missions.models import Claim, EvidenceFile, Mission


class Command(BaseCommand):
    help = "Добавя осем седмици измислена активност към демо данните."

    @transaction.atomic
    def handle(self, *args, **options):
        if User.objects.exclude(email__endswith=DOMAIN).exists():
            raise CommandError("В базата има истински потребители: командата е само за демо база.")
        if not Mission.objects.exists():
            raise CommandError("Първо пуснете python manage.py seed_demo.")
        if Claim.objects.exists():
            raise CommandError("Вече има активност. За ново начало пуснете python manage.py reset_demo.")
        Story().run()
        self.stdout.write(self.style.SUCCESS(
            f"Готово: {Claim.objects.count()} заявки, {EvidenceFile.objects.count()} файла към тях, "
            f"{XPTransaction.objects.filter(amount__gt=0).count()} движения на XP."))
