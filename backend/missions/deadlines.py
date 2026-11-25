"""
Срокът на мисия или домашна за конкретен ученик.

Обикновено е срокът на самата мисия. Може да е по-късен, когато:
  - ученикът е използвал „Удължен срок“ (DeadlineExtension) – само за него;
  - заявката му е върната: винаги има още малко време да я поправи, дори срокът да е минал.
Дните са в „Настройки на играта“.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .errors import GameRuleError
from .models import Claim, DeadlineExtension, Mission

PASS_CODE = "deadline_pass"


def _rules():
    from economy.models import GameSettings  # тук, за да няма кръгов импорт

    return GameSettings.load()


def deadline_for(student, mission, claim=None):
    """До кога този ученик може да подаде. claim – заявката му, ако вече е намерена."""
    extension = DeadlineExtension.objects.filter(mission=mission, student=student).first()
    moments = [mission.deadline]
    if extension:
        moments.append(extension.until)
    if claim is None:
        claim = Claim.objects.filter(mission=mission, student=student).first()
    if claim is not None and claim.status == Claim.Status.REJECTED and claim.reviewed_at:
        moments.append(claim.reviewed_at + timedelta(days=_rules().resubmit_days))
    return max(moments)


def can_submit(student, mission, claim=None):
    return mission.is_active and timezone.now() <= deadline_for(student, mission, claim)


def apply_extensions(student, missions):
    """За показване: сменя (само в паметта) срока на мисиите, които ученикът си е удължил."""
    missions = list(missions)
    until = dict(DeadlineExtension.objects.filter(student=student, mission__in=[m.pk for m in missions])
                 .values_list("mission_id", "until"))
    for mission in missions:
        mission.is_extended = mission.pk in until
        if mission.is_extended:
            mission.deadline = max(mission.deadline, until[mission.pk])
    return missions


def with_extension(claims):
    """Добавя claim.is_extended към заявките, за да го вижда учителят."""
    return claims.annotate(is_extended=Exists(DeadlineExtension.objects.filter(
        mission=OuterRef("mission"), student=OuterRef("student"))))


# ---------- „Удължен срок“ ----------

def unused_passes(student):
    return student.purchases.filter(privilege__code=PASS_CODE, used_at__isnull=True).order_by("purchased_at")


def why_not_extend(student, mission, now=None):
    """Защо срокът не може да се удължи; празен текст – може (ако ученикът има „Удължен срок“)."""
    now = now or timezone.now()
    rules = _rules()
    if not mission.is_active or not mission.is_visible_to(student):
        return "Мисията не приема заявки."
    if not mission.extensions_allowed:
        return "За тази мисия срокът не се удължава."
    if Claim.objects.filter(mission=mission, student=student).exclude(status=Claim.Status.REJECTED).exists():
        return "Вече си подал заявка."
    if DeadlineExtension.objects.filter(mission=mission, student=student).exists():
        return "Срокът вече е удължен. Може само веднъж."
    if now > mission.deadline + timedelta(days=rules.extension_late_days):
        return f"Срокът може да се удължи най-късно {rules.extension_late_days} дни след като е минал."
    return ""


def use_pass(student, mission):
    """Ученикът използва купения „Удължен срок“. Мести срока само за него."""
    from accounts.models import User

    if not student.is_student:
        raise GameRuleError("Само ученици удължават срок.")
    now = timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().get(pk=student.pk)  # двойно натискане не харчи два
        problem = why_not_extend(student, mission, now)
        if problem:
            raise GameRuleError(problem)
        purchase = unused_passes(student).first()
        if purchase is None:
            raise GameRuleError("Нямаш „Удължен срок“. Можеш да го вземеш от магазина.")
        purchase.used_at, purchase.used_for_mission = now, mission
        purchase.save(update_fields=["used_at", "used_for_mission"])
        # Поне един ден, дори при странни настройки.
        until = max(mission.deadline + timedelta(days=_rules().extension_days), now + timedelta(days=1))
        return DeadlineExtension.objects.create(mission=mission, student=student, purchase=purchase, until=until)


def missions_to_extend(student):
    """Наскоро изтеклите мисии, чийто срок ученикът още може да удължи."""
    from .services import visible_to

    now = timezone.now()
    missions = (Mission.objects.filter(visible_to(student), is_active=True, extensions_allowed=True, deadline__lt=now,
                                       deadline__gte=now - timedelta(days=_rules().extension_late_days))
                .exclude(claims__student=student).exclude(extensions__student=student).select_related("guild"))
    return missions.order_by("deadline")
