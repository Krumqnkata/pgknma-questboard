"""
Аватари на учениците – рисуват се от сървъра, без снимки.

Шарката е 5×5 квадратчета, огледални отляво надясно (като иконите в GitHub).
Кои квадратчета са запълнени, се решава от SHA-256 на номера на ученика и
числото avatar_seed. Ученикът може да поиска „нова шарка“ – тогава числото
се увеличава с 1 и шарката става друга. Цветът е цветът на гилдията, а
рамката (ако е купена) се добавя с CSS клас.
"""
import hashlib

from django.utils.safestring import mark_safe
from django.utils.text import slugify

SIZE = 5


def cells_for(user):
    """Кои квадратчета (колона, ред) са запълнени. Винаги поне 5, за да не е празна шарката."""
    digest = hashlib.sha256(f"questboard:{user.pk}:{user.avatar_seed}".encode()).digest()
    bits = int.from_bytes(digest[:8], "big")
    half = (SIZE + 1) // 2  # 3 колони; другите 2 са огледални
    cells = set()
    for row in range(SIZE):
        for col in range(half):
            if bits >> (row * half + col) & 1:
                cells.update({(col, row), (SIZE - 1 - col, row)})
    if len(cells) < 5:
        cells.update({(2, row) for row in range(SIZE)})  # средната колона
    return sorted(cells)


def avatar_html(user, size=40, frame_style=None):
    """
    HTML на аватара: <span> с цвета на гилдията и рамката, вътре SVG.
    frame_style – друга рамка за преглед (в магазина), вместо сложената.
    """
    classes = ["avatar"]
    if getattr(user, "guild", None):
        classes.append(f"guild-{slugify(str(user.guild))}")
    if frame_style is None:
        frame = getattr(user, "shown_frame", None)
        frame_style = frame.frame_style if frame else ""
    if frame_style:
        classes.append(f"frame-{slugify(frame_style)}")
    squares = "".join(f'<rect x="{x + 1}" y="{y + 1}" width="1" height="1" rx="0.18"/>' for x, y in cells_for(user))
    return mark_safe(
        f'<span class="{" ".join(classes)}" style="--avatar-size:{int(size)}px" aria-hidden="true">'
        f'<svg viewBox="0 0 7 7" fill="currentColor">{squares}</svg></span>'
    )
