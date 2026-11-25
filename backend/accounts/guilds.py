"""
Гилдиите на ученика: най-много две, едната е основна.

От основната идват видът на сайта и цветът на аватара, а XP на ученика се брои само за
нея в класацията на гилдиите (иначе едни и същи точки биха вдигнали две гилдии).
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from missions.errors import GameRuleError

from .models import MAX_GUILDS, User

MAIN_CHANGE_DAYS = 30


def can_join(student, guild_id):
    return guild_id not in student.guild_ids and len(student.guild_ids) < MAX_GUILDS


def join_guild(student, guild):
    """Добавя гилдията: първата е основна, втората не. Връща False, ако няма място."""
    if not can_join(student, guild.pk):
        return False
    if student.guild_id is None:
        student.guild = guild
    else:
        student.second_guild = guild
    student.save(update_fields=["guild", "second_guild"])
    return True


def remove_guild(student, guild_id):
    """Маха гилдията; ако е основната, втората заема мястото ѝ."""
    if guild_id == student.guild_id:
        student.guild = student.second_guild
        student.second_guild = None
    elif guild_id == student.second_guild_id:
        student.second_guild = None
    else:
        return False
    student.save(update_fields=["guild", "second_guild"])
    return True


def leave_guild(student, guild):
    with transaction.atomic():
        student = User.objects.select_for_update().get(pk=student.pk)
        if not remove_guild(student, guild.pk):
            raise GameRuleError("Не си в тази гилдия.")


def next_main_change(student):
    """Кога може пак да смени основната гилдия; None – веднага."""
    if student.main_guild_changed_at is None:
        return None
    moment = student.main_guild_changed_at + timedelta(days=MAIN_CHANGE_DAYS)
    return moment if moment > timezone.now() else None


def make_main(student, guild):
    with transaction.atomic():
        student = User.objects.select_for_update().get(pk=student.pk)
        if student.second_guild_id != guild.pk:
            raise GameRuleError("Само втората ти гилдия може да стане основна.")
        wait = next_main_change(student)
        if wait:
            raise GameRuleError(f"Основната гилдия се сменя веднъж на {MAIN_CHANGE_DAYS} дни. "
                                f"Следващата смяна е възможна от {timezone.localtime(wait):%d.%m.%Y}.")
        student.guild, student.second_guild = student.second_guild, student.guild
        student.main_guild_changed_at = timezone.now()
        student.save(update_fields=["guild", "second_guild", "main_guild_changed_at"])
