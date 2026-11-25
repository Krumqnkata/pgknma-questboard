"""
Гилдия „Изследователи“ се маха. Нищо от учениците не се губи: научните мисии минават
към „Техничари“ (старите тестове на гилдията също, но спрени), а членовете ѝ остават
без гилдия или с втората си и могат да влязат в друга с входен тест.
"""
from django.db import migrations

NAME = "Изследователи"
HEIR = "techies"
DESCRIPTION = "Компютри, роботика, техника и всичко, което трябва да се поправи."
NEW_DESCRIPTION = "Компютри, роботика, техника, наука и опити."


def forward(apps, schema_editor):
    Guild = apps.get_model("accounts", "Guild")
    User = apps.get_model("accounts", "User")
    heir = Guild.objects.filter(code=HEIR).first()
    old = Guild.objects.filter(code="explorers", name=NAME).first()
    if old is not None and heir is not None:
        User.objects.filter(second_guild=old).update(second_guild=None)
        for student in User.objects.filter(guild=old):
            student.guild_id, student.second_guild_id = student.second_guild_id, None
            student.save(update_fields=["guild", "second_guild"])
        apps.get_model("missions", "Mission").objects.filter(guild=old).update(guild=heir)
        apps.get_model("quizzes", "GuildTest").objects.filter(guild=old).update(guild=heir, is_active=False)
        apps.get_model("badges", "Badge").objects.filter(guild=old).update(guild=heir, is_active=False)
        old.delete()
        Guild.objects.filter(pk=heir.pk, description=DESCRIPTION).update(description=NEW_DESCRIPTION)
    # Гилдии, добавени от администратора със стария цвят.
    Guild.objects.filter(code="explorers").update(code="helpers")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_second_guild"),
        ("missions", "0004_homework"),
        ("quizzes", "0002_remove_previous_guild"),
        ("badges", "0008_initial_mission_badges"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
