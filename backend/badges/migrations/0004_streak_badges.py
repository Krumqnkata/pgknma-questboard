"""Значки за серии: поредни седмици с поне една потвърдена мисия. ПРИМЕРНИ – сменят се от администрацията."""
from django.db import migrations

BADGES = [
    ("Три седмици подред", "Изпълни мисия 3 седмици подред.", 3, 7),
    ("Пет седмици подред", "Изпълни мисия 5 седмици подред.", 5, 8),
    ("Десет седмици подред", "Изпълни мисия 10 седмици подред.", 10, 9),
]


def create_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    for name, description, threshold, order in BADGES:
        Badge.objects.get_or_create(name=name, defaults={
            "description": description, "icon": "flame", "rule": "streak", "threshold": threshold, "order": order,
        })


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0003_streak_rule"),
    ]

    operations = [
        migrations.RunPython(create_badges, migrations.RunPython.noop),
    ]
