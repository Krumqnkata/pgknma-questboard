"""
Начални данни: настройките на играта, примерни нива и двете привилегии.

Границите на нивата и цените са ПРИМЕРНИ – в плана са „за решаване“.
Променят се от Django admin.
"""
from django.db import migrations

LEVELS = [
    (1, 0, "Новак"),
    (2, 100, "Чирак"),
    (3, 250, "Майстор"),
    (4, 500, "Ветеран"),
    (5, 1000, "Легенда"),
]

PRIVILEGES = [
    ("deadline_pass", "Deadline Pass", "Удължен срок за предаване на задача.", 3),
    ("hint_token", "Hint Token", "Една подсказка от асистента по конкретна мисия.", 2),
]


def create_initial_data(apps, schema_editor):
    GameSettings = apps.get_model("economy", "GameSettings")
    Level = apps.get_model("economy", "Level")
    Privilege = apps.get_model("economy", "Privilege")

    GameSettings.objects.get_or_create(pk=1)

    for number, min_xp, title in LEVELS:
        Level.objects.get_or_create(number=number, defaults={"min_xp": min_xp, "title": title})

    for code, name, description, price in PRIVILEGES:
        Privilege.objects.get_or_create(
            code=code, defaults={"name": name, "description": description, "price": price},
        )


class Migration(migrations.Migration):
    dependencies = [("economy", "0001_initial")]

    operations = [migrations.RunPython(create_initial_data, migrations.RunPython.noop)]
