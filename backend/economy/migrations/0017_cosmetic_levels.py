"""
Титлите и рамките се отключват според нивото, а титлата „Откривател“ се печели
само от мисия. ПРИМЕРНИ – сменят се от „Игра“ → „Магазин“.
"""
from django.db import migrations

LEVELS = {"title_lightning": 2, "title_strategist": 3, "title_legend": 5,
          "frame_neon": 2, "frame_gold": 4, "frame_rainbow": 5}


def set_levels(apps, schema_editor):
    Privilege = apps.get_model("economy", "Privilege")
    Level = apps.get_model("economy", "Level")
    top = Level.objects.order_by("-number").values_list("number", flat=True).first() or 1
    for code, level in LEVELS.items():
        # Предмет с ниво над най-високото никога не би се отключил.
        Privilege.objects.filter(code=code, min_level=1).update(min_level=min(level, top))
    Privilege.objects.get_or_create(code="title_discoverer", defaults={
        "kind": "title", "name": "Откривател", "description": "Печели се само от специална мисия.",
        "price": 1, "only_from_mission": True,
    })


class Migration(migrations.Migration):

    dependencies = [("economy", "0016_sponsors_and_levels")]

    operations = [migrations.RunPython(set_levels, migrations.RunPython.noop)]
