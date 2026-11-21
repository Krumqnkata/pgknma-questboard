"""Собствени филтри и тагове за шаблоните. Зареждат се с {% load questboard %}."""
from django import template
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
