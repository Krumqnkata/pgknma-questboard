"""Попълва колко монети е дало всяко старо движение на XP – за да може и то да се отмени правилно."""
from datetime import timedelta

from django.db import migrations
from django.db.models import Sum


def backfill(apps, schema_editor):
    XPTransaction = apps.get_model("economy", "XPTransaction")
    CoinTransaction = apps.get_model("economy", "CoinTransaction")
    for entry in XPTransaction.objects.filter(amount__gt=0, coins=0):
        earned = CoinTransaction.objects.filter(student_id=entry.student_id, kind="earned")
        if entry.claim_id:
            earned = earned.filter(claim_id=entry.claim_id)
        else:  # бонус: монетите са записани в същия миг от същия учител
            earned = earned.filter(claim__isnull=True, created_by_id=entry.created_by_id,
                                   created_at__gte=entry.created_at, created_at__lte=entry.created_at + timedelta(seconds=5))
        coins = earned.aggregate(total=Sum("amount"))["total"] or 0
        if coins:
            entry.coins = coins
            entry.save(update_fields=["coins"])


class Migration(migrations.Migration):

    dependencies = [
        ("economy", "0014_undo_rewards"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
