"""Имената на привилегиите в условията за ползване. Само ако текстът не е пренаписан."""
from django.db import migrations

OLD, NEW = "(например Deadline Pass и Hint Token)", "(например удължен срок и подсказка)"


def rename(apps, schema_editor):
    SitePage = apps.get_model("web", "SitePage")
    for page in SitePage.objects.filter(content__contains=OLD):
        page.content = page.content.replace(OLD, NEW)
        page.save(update_fields=["content"])


class Migration(migrations.Migration):
    dependencies = [("web", "0007_privacy_leaders")]

    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
