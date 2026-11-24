"""
Код на гилдията – по него сайтът избира цвета и иконата.
Отделно от преименуването (0008): в MySQL промяната на таблица не се връща назад,
затова всяка миграция прави само едно нещо.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_avatar_and_cosmetics")]

    operations = [
        migrations.AddField(
            model_name="guild", name="code",
            field=models.CharField(
                choices=[("helpers", "Помощници (син, щит)"), ("artists", "Артисти (розов, четка)"),
                         ("techies", "Техничари (оранжев, гаечен ключ)"), ("explorers", "Изследователи (зелен, компас)"),
                         ("athletes", "Спортисти (червен, мълния)"), ("organizers", "Организатори (лилав, хора)")],
                default="explorers", help_text="Определя цвета и иконата на гилдията в сайта.",
                max_length=12, verbose_name="цвят и икона"),
        ),
    ]
