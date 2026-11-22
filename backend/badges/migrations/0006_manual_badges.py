"""Значки, които учителят дава ръчно. ПРИМЕРНИ – сменят се и се добавят от администрацията."""
from django.db import migrations

BADGES = [
    ("Звезда на седмицата", "Учителят те отличи за седмицата.", "star", 20),
    ("Отборен играч", "Помогна на съучениците си.", "shield", 21),
    ("Златна идея", "Предложи идея, която промени нещо в училище.", "bolt", 22),
]


def create_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    for name, description, icon, order in BADGES:
        Badge.objects.get_or_create(name=name, defaults={
            "description": description, "icon": icon, "rule": "manual", "threshold": 1, "order": order,
        })


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0005_rewards"),
    ]

    operations = [
        migrations.RunPython(create_badges, migrations.RunPython.noop),
    ]
