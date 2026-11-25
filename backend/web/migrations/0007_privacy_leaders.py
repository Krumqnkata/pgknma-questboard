"""Политиката за поверителност: отговорникът на гилдията вижда резултата от тестовете ѝ. Само ако текстът не е пренаписан."""
from django.db import migrations

OLD = "Виждат ги ученикът (резултата), учителят, пуснал теста, и администраторът."
NEW = ("Виждат ги ученикът (резултата), учителят, пуснал теста, отговорникът на гилдията (само резултата и членовете ѝ) "
       "и администраторът.")


def update_privacy(apps, schema_editor):
    SitePage = apps.get_model("web", "SitePage")
    for page in SitePage.objects.filter(slug="privacy", content__contains=OLD):
        page.content = page.content.replace(OLD, NEW)
        page.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [("web", "0006_privacy_tests")]

    operations = [migrations.RunPython(update_privacy, migrations.RunPython.noop)]
