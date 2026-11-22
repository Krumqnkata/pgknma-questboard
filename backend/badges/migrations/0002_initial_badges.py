"""
Начални значки. Те са ПРИМЕРНИ – администраторът ги променя, изключва или
добавя нови от администрацията („Игра“ → „Значки“).
"""
from django.db import migrations

BADGES = [
    # име, описание, икона, правило, праг
    ("Първа мисия", "Изпълни първата си мисия.", "flag", "missions", 1),
    ("Пет мисии", "Изпълни 5 мисии.", "star", "missions", 5),
    ("Верен на гилдията", "Изпълни 5 мисии в една и съща гилдия.", "shield", "guild_missions", 5),
    ("Десет мисии", "Изпълни 10 мисии.", "crown", "missions", 10),
    ("Майстор", "Стигни ниво 3.", "bolt", "level", 3),
    ("Пръв в магазина", "Купи първата си привилегия.", "bag", "purchases", 1),
]


def create_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    for order, (name, description, icon, rule, threshold) in enumerate(BADGES, start=1):
        Badge.objects.get_or_create(name=name, defaults={
            "description": description, "icon": icon, "rule": rule, "threshold": threshold, "order": order,
        })


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_badges, migrations.RunPython.noop),
    ]
