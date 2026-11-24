"""
Политиката за поверителност: тестовете на гилдиите и домашните. Добавя се след реда
за игровите данни, само ако училището не го е пренаписало.
"""
from django.db import migrations

START = "- Игра: заявките за мисии и доказателствата към тях"
NEW = (
    "- Тестове: отговорите, времето за тях, резултатът и колко пъти страницата е напусната по време на теста. "
    "Виждат ги ученикът (резултата), учителят, пуснал теста, и администраторът."
)


def update_privacy(apps, schema_editor):
    SitePage = apps.get_model("web", "SitePage")
    for page in SitePage.objects.filter(slug="privacy"):
        if NEW in page.content:
            continue
        lines = page.content.split("\n")
        for number, line in enumerate(lines):
            if line.startswith(START):
                lines.insert(number + 1, NEW)
                page.content = "\n".join(lines)
                page.save(update_fields=["content"])
                break


class Migration(migrations.Migration):

    dependencies = [("web", "0005_privacy_cookies")]

    operations = [migrations.RunPython(update_privacy, migrations.RunPython.noop)]
