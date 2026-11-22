"""
Смяна на псевдонима от самия ученик (от „Профил“).

Псевдонимът е единственото, което другите ученици виждат в класациите,
затова смяната има правила:
  - от 3 до 20 знака: букви, цифри, интервал, „-“ и „_“;
  - не може да е зает от друг (без значение главни или малки букви);
  - не може да съдържа истинското име или фамилия на ученика;
  - не може да съдържа забранена дума (списъкът е в „Настройки на играта“);
  - най-много веднъж на няколко дни (също от настройките, 0 – без ограничение).
Всяка смяна се записва в историята (NicknameChange).
"""
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import formats, timezone

from .models import NicknameChange, User

MIN_LENGTH, MAX_LENGTH = 3, 20
ALLOWED = re.compile(r"^[\w\- ]+$")  # \w – букви от всяка азбука, цифри и „_“


def _rules():
    from economy.models import GameSettings  # тук, за да няма кръгов import

    return GameSettings.load()


def tidy(value):
    """Маха излишните интервали: „  Сив   Вълк “ → „Сив Вълк“."""
    return " ".join((value or "").split())


def validate_nickname(student, value):
    """Проверява новия псевдоним и го връща подреден. При проблем – ValidationError с обяснение."""
    nickname = tidy(value)
    if not MIN_LENGTH <= len(nickname) <= MAX_LENGTH:
        raise ValidationError(f"Псевдонимът трябва да е от {MIN_LENGTH} до {MAX_LENGTH} знака.")
    if not ALLOWED.match(nickname):
        raise ValidationError("Позволени са само букви, цифри, интервал, „-“ и „_“.")

    folded = nickname.casefold()  # сравнение без значение главни/малки букви (и на кирилица)
    if folded == (student.nickname or "").casefold():
        raise ValidationError("Това вече е твоят псевдоним.")
    taken = User.objects.exclude(pk=student.pk).exclude(nickname=None).values_list("nickname", flat=True)
    if folded in {other.casefold() for other in taken}:
        raise ValidationError("Този псевдоним вече е зает.")
    for name in (student.first_name, student.last_name):
        if len(name) >= 3 and name.casefold() in folded:
            raise ValidationError("Псевдонимът не може да съдържа истинското ти име – иначе всички ще те познаят.")
    if any(word in folded for word in _rules().banned_word_list()):
        raise ValidationError("Псевдонимът съдържа неподходяща дума. Избери друг.")
    return nickname


def next_change_at(student):
    """Кога най-рано ученикът може пак да смени псевдонима си (None – може сега)."""
    days = _rules().nickname_change_days
    if not days:
        return None
    last = student.nickname_changes.filter(changed_by=student).first()
    if not last:
        return None
    moment = last.changed_at + timedelta(days=days)
    return moment if moment > timezone.now() else None


def change_nickname(student, value):
    """Ученикът сменя псевдонима си. Връща новия псевдоним или хвърля ValidationError."""
    if not student.is_student:
        raise ValidationError("Само учениците имат псевдоним.")
    wait_until = next_change_at(student)
    if wait_until:
        day = formats.date_format(timezone.localtime(wait_until), "j E")
        raise ValidationError(f"Псевдонимът може да се сменя веднъж на {_rules().nickname_change_days} дни. "
                              f"Следващата смяна е възможна от {day.lower()}.")
    nickname = validate_nickname(student, value)
    old = student.nickname or ""
    try:
        with transaction.atomic():
            student.nickname = nickname
            student.save(update_fields=["nickname"])
            NicknameChange.objects.create(student=student, old=old, new=nickname, changed_by=student)
    except IntegrityError:  # някой друг го е взел в същия миг
        student.nickname = old
        raise ValidationError("Този псевдоним вече е зает.")
    return nickname
