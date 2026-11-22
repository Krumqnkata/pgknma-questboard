"""
Политиката за поверителност споменава и файловете към доказателствата.
Сменят се само редовете, които още са както в началния текст – ако
училището ги е пренаписало, промените му остават.
"""
from django.db import migrations

REPLACEMENTS = [
    ('- Игра: заявките за мисии и доказателствата към тях, решенията на учителите, XP, монети, покупки, значки и известия.',
     '- Игра: заявките за мисии и доказателствата към тях (текст, снимки и PDF файлове), решенията на учителите, XP, монети, покупки, значки и известия. От снимките автоматично се махат скритите данни, например мястото, където са направени.'),
    ('- Учителите виждат имената и класа на учениците, които са подали заявка по техните мисии.',
     '- Учителите виждат имената и класа на учениците, които са подали заявка по техните мисии.\n- Снимките и файловете към заявка виждат само ученикът, учителят на мисията и администраторът.'),
]


def update_privacy(apps, schema_editor):
    SitePage = apps.get_model("web", "SitePage")
    for page in SitePage.objects.filter(slug="privacy"):
        for old, new in REPLACEMENTS:
            if old in page.content and new not in page.content:
                page.content = page.content.replace(old, new)
        page.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0002_initial_pages"),
    ]

    operations = [
        migrations.RunPython(update_privacy, migrations.RunPython.noop),
    ]
