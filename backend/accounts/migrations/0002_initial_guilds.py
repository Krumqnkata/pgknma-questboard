"""Създава четирите гилдии от документа за иновацията."""
from django.db import migrations

GUILDS = ["Builders", "Guardians", "Explorers", "Citizens"]


def create_guilds(apps, schema_editor):
    Guild = apps.get_model("accounts", "Guild")
    for name in GUILDS:
        Guild.objects.get_or_create(name=name)


def remove_guilds(apps, schema_editor):
    Guild = apps.get_model("accounts", "Guild")
    Guild.objects.filter(name__in=GUILDS, members__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(create_guilds, remove_guilds)]
