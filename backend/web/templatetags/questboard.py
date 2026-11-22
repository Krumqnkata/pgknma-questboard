"""Собствени филтри и тагове за шаблоните. Зареждат се с {% load questboard %}."""
from django import template
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from economy.words import coins_text

register = template.Library()


@register.filter
def coins(count):
    """{{ 3|coins }} → „3 монети“"""
    return coins_text(count)


@register.filter
def guild_class(guild):
    """CSS клас с цвета на гилдията: {{ mission.guild|guild_class }} → „guild-builders“."""
    return f"guild-{slugify(str(guild))}" if guild else ""


def _value_tokens(value):
    """Превръща стойност в оцветени части, като в редактор на код."""
    if isinstance(value, bool):
        return [("key", "true" if value else "false")]
    if isinstance(value, (int, float)):
        return [("num", str(value))]
    if value is None:
        return [("key", "null")]
    if isinstance(value, (list, tuple)):
        tokens = [("", "[")]
        for i, item in enumerate(value):
            if i:
                tokens.append(("", ", "))
            tokens += _value_tokens(item)
        return tokens + [("", "]")]
    return [("str", f'"{value}"')]


@register.inclusion_tag("web/_code_card.html")
def code_card(filename, variable, fields, comment="", aside=""):
    """
    Панел като редактор на код с истински данни, напр.:
        {% code_card "player.ts" "player" player_fields "Твоят профил" %}
    fields е списък от двойки (име, стойност). Текстът се екранира от шаблона.
    """
    lines = []
    if comment:
        lines.append([("com", f"// {comment}")])
    lines.append([("key", "export const"), ("", f" {variable} = {{")])
    for name, value in fields:
        lines.append([("", f"  {name}: "), *_value_tokens(value), ("", ",")])
    lines.append([("", "} "), ("key", "as const"), ("", ";")])
    return {"filename": filename, "lines": lines, "aside": aside}


# Иконите на значките – прости линии, които взимат цвета на текста (работят и в тъмната тема).
BADGE_ICONS = {
    "flag": '<path d="M5 21V4m0 0h11l-2 4 2 4H5"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "crown": '<path d="m3 8 4.5 4L12 5l4.5 7L21 8l-2 11H5z"/>',
    "shield": '<path d="m12 3 8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "bag": '<path d="M5 8h14l-1 13H6zM9 8V6a3 3 0 0 1 6 0v2"/>',
}


@register.simple_tag
def badge_icon(name):
    """{% badge_icon badge.icon %} → SVG икона. Иконите са само от списъка по-горе."""
    path = BADGE_ICONS.get(name, BADGE_ICONS["star"])
    return mark_safe(
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )
