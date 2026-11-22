"""
Начални артикули „за профила“: титли и рамки на аватара. Те са ПРИМЕРНИ –
цените и имената се сменят от администрацията („Игра“ → „Магазин“).
"""
from django.db import migrations

ITEMS = [
    # код, вид, име, описание, цена, рамка
    ("title_lightning", "title", "Мълния", "Титла до псевдонима в класацията.", 3, ""),
    ("title_strategist", "title", "Стратег", "Титла до псевдонима в класацията.", 4, ""),
    ("title_legend", "title", "Легенда", "Титла до псевдонима в класацията.", 8, ""),
    ("frame_gold", "frame", "Златна рамка", "Рамка около аватара.", 5, "gold"),
    ("frame_neon", "frame", "Неонова рамка", "Рамка около аватара.", 5, "neon"),
    ("frame_rainbow", "frame", "Рамка „Дъга“", "Рамка около аватара.", 7, "rainbow"),
]


def create_items(apps, schema_editor):
    Privilege = apps.get_model("economy", "Privilege")
    for code, kind, name, description, price, frame in ITEMS:
        Privilege.objects.get_or_create(code=code, defaults={
            "kind": kind, "name": name, "description": description, "price": price, "frame_style": frame,
        })


class Migration(migrations.Migration):

    dependencies = [
        ("economy", "0010_shop_cosmetics"),
    ]

    operations = [
        migrations.RunPython(create_items, migrations.RunPython.noop),
    ]
