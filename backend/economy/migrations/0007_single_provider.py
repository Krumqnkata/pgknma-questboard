"""
Асистентът вече ползва един избран доставчик вместо основен + резервни.

Моделът на избрания доставчик се пренася в новото поле „модел“. Ако е
препоръчаният, полето остава празно (тогава се ползва препоръчаният).
"""
from django.db import migrations, models

DEFAULT_MODELS = {"claude": "claude-opus-5-5", "gemini": "gemini-3.5-flash-lite", "openai": "gpt-5-mini"}


def keep_chosen_model(apps, schema_editor):
    GameSettings = apps.get_model("economy", "GameSettings")
    for rules in GameSettings.objects.all():
        chosen = {"claude": rules.claude_model, "openai": rules.openai_model,
                  "gemini": rules.gemini_model}.get(rules.llm_provider, "").strip()
        rules.llm_model = "" if chosen == DEFAULT_MODELS.get(rules.llm_provider) else chosen
        rules.save(update_fields=["llm_model"])


class Migration(migrations.Migration):

    dependencies = [
        ("economy", "0006_login_lockout"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamesettings",
            name="llm_model",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="модел",
                help_text="Празно – препоръчаният модел: Claude – claude-opus-5-5, Gemini – gemini-3.5-flash-lite, "
                          "OpenAI – gpt-5-mini. След промяна запазете и натиснете „Провери асистента“.",
            ),
        ),
        migrations.RunPython(keep_chosen_model, migrations.RunPython.noop),
        migrations.RemoveField(model_name="gamesettings", name="use_other_providers"),
        migrations.RemoveField(model_name="gamesettings", name="claude_model"),
        migrations.RemoveField(model_name="gamesettings", name="openai_model"),
        migrations.RemoveField(model_name="gamesettings", name="gemini_model"),
        migrations.AlterField(
            model_name="gamesettings",
            name="llm_provider",
            field=models.CharField(
                choices=[("openai", "OpenAI"), ("gemini", "Google Gemini"), ("claude", "Anthropic Claude")],
                default="claude", max_length=10, verbose_name="доставчик",
                help_text="Ключът за избрания доставчик трябва да е в .env "
                          "(ANTHROPIC_API_KEY, GEMINI_API_KEY или OPENAI_API_KEY).",
            ),
        ),
    ]
