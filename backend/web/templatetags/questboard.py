"""Собствени филтри и тагове за шаблоните. Зареждат се с {% load questboard %}."""
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from economy.words import coins_text

register = template.Library()


@register.filter
def coins(count):
    """{{ 3|coins }} → „3 монети“"""
    return coins_text(count)


@register.filter
def guild_class(guild):
    """CSS клас с цвета на гилдията: {{ mission.guild|guild_class }} → „guild-techies“."""
    return f"guild-{guild.code}" if guild else ""


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
        {% code_card "quest.ts" "quest" mission_fields "Най-новата активна мисия" %}
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
    "coin": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/>',
    # Икони на гилдиите в горната лента на картата с мисия
    "wrench": '<path d="M7 10h3V7L6.5 3.5a6 6 0 0 1 8 8l6 6a2 2 0 0 1-3 3l-6-6a6 6 0 0 1-8-8z"/>',
    "book": '<path d="M12 6C9 4 6 4 3 5v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1zM12 6v14"/>',
    "brush": '<path d="M14 4.5 19.5 10 11 18.5 5.5 13zM5.5 13c-2 1-2.5 3-2.5 5.5V21h2.5c2.5 0 4.5-.5 5.5-2.5"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m8 16 2-6 6-2-2 6z"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20a6 6 0 0 1 12 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14c2 .6 3 2.6 3 6"/>',
    "flame": '<path d="M12 22c4 0 7-2.7 7-6.8 0-3.6-2.4-6-4.3-8.2-.4 2-1.6 3.4-3.2 3.9.6-3.1-.6-6.5-3.5-8.9 '
             '.3 3.6-1.6 5.7-3 7.8A8 8 0 0 0 5 15.2C5 19.3 8 22 12 22z"/>',
}


@register.simple_tag
def badge_icon(name):
    """{% badge_icon badge.icon %} → SVG икона. Иконите са само от списъка по-горе."""
    path = BADGE_ICONS.get(name, BADGE_ICONS["star"])
    return mark_safe(
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )


@register.filter
def page_text(text, school=None):
    """
    Превръща текста на страница от администрацията в HTML:
    празен ред – нов абзац, „## “ – заглавие, „- “ – точка от списък.
    Всеки ред се екранира, затова в текста не може да се вмъкне HTML или скрипт.
    „[училище]“ и „[имейл]“ се заменят с данните от „Настройки на играта“.
    """
    school = school or {}
    replacements = {
        "[училище]": escape(school.get("name") or "училището"),
        "[имейл]": escape(school.get("email") or "администратора на платформата"),
    }
    html, paragraph, items = [], [], []

    def flush():
        if paragraph:
            html.append("<p>" + " ".join(paragraph) + "</p>")
            paragraph.clear()
        if items:
            html.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            items.clear()

    for raw in (text or "").splitlines():
        line = escape(raw.strip())
        for placeholder, value in replacements.items():
            line = line.replace(escape(placeholder), value)
        if not line:
            flush()
        elif line.startswith("## "):
            flush()
            # Съобщението за бисквитките води направо до този раздел (/privacy/#cookies).
            anchor = ' id="cookies"' if line[3:].startswith("Бисквитки") else ""
            html.append(f"<h2{anchor}>{line[3:]}</h2>")
        elif line.startswith("- "):
            if paragraph:
                flush()
            items.append(line[2:])
        else:
            if items:
                flush()
            paragraph.append(line)
    flush()
    return mark_safe("\n".join(html))


@register.filter
def theme_class(user):
    """Темата на сайта: на основната гилдия, на учителите или на администратора. Без тема – гости и ученик без гилдия."""
    if not getattr(user, "is_authenticated", False):
        return ""
    name = user.guild.code if user.is_student and user.guild else "" if user.is_student else user.role
    return f"themed accent-{name}" if name else ""


GUILD_ICONS = {"helpers": "shield", "artists": "brush", "techies": "wrench",
               "athletes": "bolt", "organizers": "users"}


@register.simple_tag
def guild_icon(guild):
    """{% guild_icon mission.guild %} → иконата на гилдията."""
    return badge_icon(GUILD_ICONS.get(getattr(guild, "code", ""), "users"))


@register.simple_tag
def avatar(user, size=40, frame_style=None):
    """{% avatar user 40 %} → аватарът на ученика (web/avatars.py). В магазина – с рамка за преглед."""
    from web.avatars import avatar_html

    return avatar_html(user, size, frame_style)


@register.filter
def difficulty(xp, max_xp):
    """
    Трудност на мисия според XP спрямо най-многото позволено:
    до 1/3 – лесна (бронзова карта), до 2/3 – средна (сребърна), над това – трудна (златна).
    """
    share = (xp or 0) / (max_xp or 1)
    if share <= 1 / 3:
        return {"slug": "easy", "name": "Лесна", "rarity": "Бронз", "card": "бронзова карта", "pips": 1}
    if share <= 2 / 3:
        return {"slug": "medium", "name": "Средна", "rarity": "Сребро", "card": "сребърна карта", "pips": 2}
    return {"slug": "hard", "name": "Трудна", "rarity": "Злато", "card": "златна карта", "pips": 3}


@register.filter
def time_left(deadline):
    """Колко остава до срока: „последен ден“, „остава 1 ден“, „остават 3 дни“."""
    import math

    from django.utils import timezone

    hours = (deadline - timezone.now()).total_seconds() / 3600
    if hours <= 24:
        return "последен ден"
    days = math.ceil(hours / 24)
    return "остава 1 ден" if days == 1 else f"остават {days} дни"
