"""
Политиката за поверителност: точните бисквитки, разговорът с асистента, отборите
и заместниците. Сменят се само редовете, които още са както в началния текст –
ако училището ги е пренаписало, промените му остават.
"""
from django.db import migrations

COOKIES = (
    "Сайтът ползва само необходимите бисквитки: за входа (сесия) и за защита на формите (CSRF). "
    "Изборът на светла или тъмна тема се пази в браузъра."
)
NEW_COOKIES = (
    "Сайтът ползва само необходимите бисквитки: sessionid за входа (изтрива се при изход) и csrftoken за защита "
    "на формите. Ако сайтът е зад защитна услуга като Cloudflare, тя може да запише и своя техническа бисквитка. "
    "В браузъра се пазят избраната тема и дали сте видели съобщението за бисквитките, а разговорът с асистента – "
    "само в отворения раздел, докато не излезете."
)
FILES = "- Снимките и файловете към заявка виждат само ученикът, учителят на мисията и администраторът."
NEW_FILES = (
    "- Снимките и файловете към заявка виждат само ученикът, отборът му при отборна мисия, учителите, които "
    "проверяват мисията, и администраторът."
)
REPLACEMENTS = [(COOKIES, NEW_COOKIES), (FILES, NEW_FILES)]


def update_privacy(apps, schema_editor):
    SitePage = apps.get_model("web", "SitePage")
    for page in SitePage.objects.filter(slug="privacy"):
        for old, new in REPLACEMENTS:
            page.content = page.content.replace(old, new)
        page.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [("web", "0004_bot_knocks")]

    operations = [migrations.RunPython(update_privacy, migrations.RunPython.noop)]
