"""Значки, които се печелят само от мисия. ПРИМЕРНИ – сменят се и се добавят от администрацията."""
from django.db import migrations

BADGES = [
    ("Екипен дух", "Изпълни отборна мисия заедно със съучениците си.", "shield", 30),
    ("Първооткривател", "Изпълни специална мисия.", "flag", 31),
]


def create_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    for name, description, icon, order in BADGES:
        Badge.objects.get_or_create(name=name, defaults={
            "description": description, "icon": icon, "rule": "mission", "threshold": 1, "order": order,
        })


class Migration(migrations.Migration):

    dependencies = [("badges", "0007_mission_badges")]

    operations = [migrations.RunPython(create_badges, migrations.RunPython.noop)]
