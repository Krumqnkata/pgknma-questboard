"""Кой ученик колко е напреднал и кои значки е заслужил."""
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count
from django.urls import reverse

from .models import Badge, StudentBadge


@dataclass
class Progress:
    """Числата, по които се проверяват всички правила."""

    missions: int = 0
    by_guild: dict = field(default_factory=dict)  # {id на гилдия: брой потвърдени мисии}
    xp: int = 0
    level: int = 0
    purchases: int = 0
    streak: int = 0

    def value_for(self, badge):
        """Докъде е стигнал ученикът по правилото на значката."""
        if badge.rule == Badge.Rule.MISSIONS:
            return self.missions
        if badge.rule == Badge.Rule.GUILD_MISSIONS:
            if badge.guild_id:
                return self.by_guild.get(badge.guild_id, 0)
            return max(self.by_guild.values(), default=0)
        if badge.rule == Badge.Rule.XP:
            return self.xp
        if badge.rule == Badge.Rule.LEVEL:
            return self.level
        if badge.rule == Badge.Rule.PURCHASES:
            return self.purchases
        if badge.rule == Badge.Rule.STREAK:
            return self.streak
        return 0


def progress_for(student):
    from economy.services import level_for_xp, streak_weeks, xp_total  # тук, за да няма кръгов import
    from missions.models import Claim

    approved = Claim.objects.filter(student=student, status=Claim.Status.APPROVED)
    by_guild = dict(approved.values_list("mission__guild").annotate(n=Count("id")).values_list("mission__guild", "n"))
    xp = xp_total(student)
    level = level_for_xp(xp)
    return Progress(
        missions=sum(by_guild.values()),
        by_guild=by_guild,
        xp=xp,
        level=level.number if level else 0,
        purchases=student.purchases.count(),
        streak=streak_weeks(student),
    )


def award_badges(student):
    """Дава на ученика всички значки, които вече е заслужил. Връща новите."""
    from notifications.models import Notification
    from notifications.services import notify

    if not student.is_student:
        return []
    owned = set(student.badges.values_list("badge_id", flat=True))
    candidates = Badge.objects.filter(is_active=True).exclude(pk__in=owned).exclude(rule=Badge.Rule.MANUAL)
    if not candidates:
        return []

    progress = progress_for(student)
    new = []
    with transaction.atomic():
        for badge in candidates:
            if progress.value_for(badge) < badge.threshold:
                continue
            _, created = StudentBadge.objects.get_or_create(student=student, badge=badge)
            if created:
                new.append(badge)
                notify(student, Notification.Kind.BADGE, f"Нова значка: „{badge.name}“ – {badge.description}",
                       link=reverse("profile"))
    return new


@dataclass
class BadgeCard:
    badge: Badge
    earned: bool
    value: int

    @property
    def percent(self):
        return min(100, int(self.value * 100 / self.badge.threshold))


def badge_cards(student):
    """Всички активни значки: първо получените, после останалите с напредъка до тях."""
    owned = set(student.badges.values_list("badge_id", flat=True))
    progress = progress_for(student)
    cards = [BadgeCard(badge, badge.pk in owned, min(progress.value_for(badge), badge.threshold))
             for badge in Badge.objects.filter(is_active=True).select_related("guild")
             if badge.rule != Badge.Rule.MANUAL or badge.pk in owned]  # ръчните – само ако са дадени
    return sorted(cards, key=lambda card: not card.earned)


def give_badge(teacher, student, badge, note=""):
    """Учителят дава значка „Дава се от учител“ на ученик (напр. „Звезда на седмицата“)."""
    from missions.services import GameRuleError
    from notifications.models import Notification
    from notifications.services import notify

    if not (teacher.is_teacher or teacher.is_admin_role):
        raise GameRuleError("Само учител може да дава значки.")
    if not (student.is_student and student.is_active):
        raise GameRuleError("Значки се дават само на ученици.")
    if badge.rule != Badge.Rule.MANUAL or not badge.is_active:
        raise GameRuleError("Тази значка не се дава ръчно.")
    note = (note or "").strip()[:200]
    with transaction.atomic():
        award, created = StudentBadge.objects.get_or_create(
            student=student, badge=badge, defaults={"given_by": teacher, "note": note})
        if not created:
            raise GameRuleError(f"{student.nickname} вече има значката „{badge.name}“.")
        text = f"Нова значка от {teacher.get_full_name() or 'учител'}: „{badge.name}“"
        notify(student, Notification.Kind.BADGE, text + (f" – {note}" if note else "."), link=reverse("profile"))
    return award


def take_badge(actor, award, why):
    """Отнема значка, дадена ръчно (напр. дадена на грешния ученик)."""
    from economy.services import can_undo
    from missions.services import GameRuleError
    from notifications.models import Notification
    from notifications.services import notify

    why = (why or "").strip()
    if len(why) < 3:
        raise GameRuleError("Напишете защо отменяте.")
    if award.badge.rule != Badge.Rule.MANUAL:
        raise GameRuleError("Отнемат се само значки, дадени от учител.")
    if not can_undo(actor, award.given_by_id, award.awarded_at):
        raise GameRuleError("Можете да отнемете само значка, която вие сте дали, и то до няколко дни след това.")
    with transaction.atomic():
        award.delete()
        notify(award.student, Notification.Kind.UNDONE, f"Значката „{award.badge.name}“ е отнета: {why[:200]}",
               link=reverse("profile"))
