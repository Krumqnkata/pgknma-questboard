"""Създава двете страници с началния текст (образец) от web/legal_defaults.py."""
from django.db import migrations


def create_pages(apps, schema_editor):
    from web.legal_defaults import DEFAULTS

    SitePage = apps.get_model("web", "SitePage")
    for slug, (title, content) in DEFAULTS.items():
        SitePage.objects.get_or_create(slug=slug, defaults={"title": title, "content": content})


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_pages, migrations.RunPython.noop),
    ]
