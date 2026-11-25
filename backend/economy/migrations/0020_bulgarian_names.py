"""Привилегиите с английски имена стават на български. Имената, сменени от администратора, не се пипат."""
from django.db import migrations

NAMES = [
    ("deadline_pass", "Deadline Pass", "Удължен срок", "Удължен срок за предаване на задача.",
     "Мести срока на мисия или домашна само за теб. Използва се от страницата ѝ."),
    ("hint_token", "Hint Token", "Подсказка", "", ""),
]


def rename(apps, schema_editor):
    Privilege = apps.get_model("economy", "Privilege")
    for code, old, new, old_text, new_text in NAMES:
        Privilege.objects.filter(code=code, name=old).update(name=new)
        if new_text:
            Privilege.objects.filter(code=code, description=old_text).update(description=new_text)


class Migration(migrations.Migration):
    dependencies = [("economy", "0019_contributors")]

    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
