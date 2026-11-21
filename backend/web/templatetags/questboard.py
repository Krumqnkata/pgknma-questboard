"""Собствени филтри за шаблоните. Зареждат се с {% load questboard %}."""
from django import template

from economy.words import coins_text

register = template.Library()


@register.filter
def coins(count):
    """{{ 3|coins }} → „3 монети“"""
    return coins_text(count)
