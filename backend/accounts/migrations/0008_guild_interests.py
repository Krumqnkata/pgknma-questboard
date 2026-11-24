"""
Гилдиите стават по интереси. Старите четири се преименуват (учениците и мисиите
остават в същата гилдия), а Артисти и Спортисти се добавят.
Описание, написано от администратора, не се пипа.
"""
from django.db import migrations

RENAMES = [
    # старо име, ново име, код, описание
    ("Guardians", "Помощници", "helpers", "Помагат на съучениците и учителите, доброволчество и поддръжка."),
    ("Builders", "Техничари", "techies", "Компютри, роботика, техника и всичко, което трябва да се поправи."),
    ("Explorers", "Изследователи", "explorers", "Наука, олимпиади, проекти и репортажи."),
    ("Citizens", "Организатори", "organizers", "Събития, кампании и ученическият съвет."),
]
NEW = [
    ("Артисти", "artists", "Изкуство, музика, театър, видео и медии."),
    ("Спортисти", "athletes", "Спорт, турнири и здравословен живот."),
]


def forward(apps, schema_editor):
    Guild = apps.get_model("accounts", "Guild")
    for old, name, code, description in RENAMES:
        guild = Guild.objects.filter(name=old).first()
        if guild is None:
            continue
        if not Guild.objects.filter(name=name).exists():  # името е уникално
            guild.name = name
        guild.code = code
        guild.description = guild.description or description
        guild.save()
    for name, code, description in NEW:
        guild, created = Guild.objects.get_or_create(name=name, defaults={"code": code, "description": description})
        if not created:
            guild.code = code
            guild.save(update_fields=["code"])


def backward(apps, schema_editor):
    Guild = apps.get_model("accounts", "Guild")
    for old, name, _code, _description in RENAMES:
        Guild.objects.filter(name=name).update(name=old)
    Guild.objects.filter(name__in=[name for name, _c, _d in NEW], members__isnull=True,
                         missions__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_guild_code")]

    operations = [migrations.RunPython(forward, backward)]
