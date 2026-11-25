"""
Кръгът на работа: какво се прави, докъде е стигнал човекът и коя е следващата му стъпка.

  Ученик:  избери → изпълни и подай → проверка → награда
  Учител:  задай → провери → награди → виж резултата

Нищо не се записва: всичко се изчислява от заявките, монетите и сроковете.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from economy.models import XPTransaction
from economy.services import active_privileges, is_unlocked, owned_cosmetics, unused_purchases, week_start_for
from economy.words import coins_text
from missions.deadlines import apply_extensions, can_submit
from missions.models import Claim, Mission
from missions.services import missions_for_student, missions_reviewed_by

SOON = timedelta(days=3)


@dataclass
class Step:
    title: str
    text: str
    link: str
    is_now: bool = False


@dataclass
class Cycle:
    headline: str         # едно изречение: какво да направя сега
    link: str = ""
    label: str = ""       # надписът на бутона
    steps: list = field(default_factory=list)


def count_text(number, one, many, none):
    return none if not number else f"{number} {one if number == 1 else many}"


def mark(steps, index):
    steps[index].is_now = True
    return steps


def days_left(deadline):
    days = (timezone.localtime(deadline).date() - timezone.localdate()).days
    return {0: "е до днес", 1: "е до утре"}.get(days, f"има срок още {days} дни")


# ---------- Ученик ----------

def student_cycle(student, stats, suggested):
    """suggested – мисиите за него от началната страница (без заявка)."""
    claims = Claim.objects.filter(student=student).select_related("mission")
    waiting = claims.filter(status=Claim.Status.PENDING).count()
    rejected = [claim for claim in claims.filter(status=Claim.Status.REJECTED, captain__isnull=True)
                if can_submit(student, claim.mission, claim) and claim.mission.is_visible_to(student)]
    open_count = missions_for_student(student).exclude(claims__student=student).count()
    missions = reverse("mission_list")
    steps = [
        Step("Избери", count_text(open_count, "отворена мисия", "отворени мисии", "няма нови мисии"), missions),
        Step("Изпълни и подай", count_text(len(rejected), "за поправяне", "за поправяне", "текст, снимка или файл"),
             reverse("mission_detail", args=[rejected[0].mission_id]) if rejected else missions),
        Step("Проверка", count_text(waiting, "чака учител", "чакат учител", "нищо не чака"), reverse("home") + "#moite-zayavki"),
        Step("Награда", f"имаш {coins_text(stats.coins)}", reverse("shop")),
    ]
    headline, link, label, now = _student_next(student, stats, suggested, rejected, waiting)
    return Cycle(headline, link, label, mark(steps, now))


def _student_next(student, stats, suggested, rejected, waiting):
    """Първото, което важи: (изречение, връзка, надпис, номер на стъпката)."""
    def to(mission):
        return reverse("mission_detail", args=[mission.pk])

    if rejected:
        mission = rejected[0].mission
        return f"„{mission.title}“ е върната. Виж какво пише учителят и я подай пак.", to(mission), "Поправи я", 1

    homework = (missions_for_student(student).filter(kind=Mission.Kind.HOMEWORK, deadline__lte=timezone.now() + SOON)
                .exclude(claims__student=student).order_by("deadline"))
    homework = next(iter(sorted(apply_extensions(student, homework), key=lambda mission: mission.deadline)), None)
    if homework:
        return f"Домашната по {homework.subject} {days_left(homework.deadline)}.", to(homework), "Към домашната", 1

    suggested = list(suggested)
    if stats.next_level:
        for mission in suggested:
            if mission.xp >= stats.xp_to_next_level:
                return (f"Още {stats.xp_to_next_level} XP до ниво {stats.next_level.number}. "
                        f"„{mission.title}“ дава {mission.xp}.", to(mission), "Виж мисията", 0)

    reward = best_reward(student, stats)
    if reward:
        return f"Имаш {coins_text(stats.coins)}. Стигат за „{reward.name}“.", reverse("shop"), "Към магазина", 3
    if suggested:
        return f"Следваща мисия за теб: „{suggested[0].title}“, +{suggested[0].xp} XP.", to(suggested[0]), "Виж мисията", 0
    if waiting:
        return "Всичко е подадено. Сега учителят проверява.", "", "", 2
    return "Няма нови мисии. Провери пак утре.", "", "", 0


def best_reward(student, stats):
    """Най-скъпото, което ученикът може да вземе сега и още го няма."""
    owned = set(owned_cosmetics(student).values_list("pk", flat=True))
    can = [item for item in active_privileges()
           if item.price <= stats.coins and is_unlocked(item, stats.level) and not item.is_sold_out and item.pk not in owned]
    return max(can, key=lambda item: item.price, default=None)


@dataclass
class FirstStep:
    title: str
    done: bool
    link: str
    hint: str


def first_steps(student, stats):
    """Списъкът за нов ученик. Празен – всичко е направено и не се показва."""
    steps = [
        FirstStep("Избери гилдия според интересите си", bool(student.guilds), reverse("guild_list"),
                  "Виж гилдиите и питай отговорника кога е входният тест."),
        FirstStep("Подай първата си заявка", Claim.objects.filter(student=student).exists(), reverse("mission_list"),
                  "Избери мисия, изпълни я и прати доказателство."),
        FirstStep("Спечели първия си XP", stats.xp > 0, reverse("mission_list"),
                  "Идва, когато учителят потвърди заявката."),
        FirstStep("Спечели първата си монета", student.coin_transactions.filter(amount__gt=0).exists(), reverse("shop"),
                  "Монетите идват от XP. С тях взимаш награди от магазина."),
    ]
    return [] if all(step.done for step in steps) else steps


# ---------- Учител ----------

def teacher_cycle(teacher, pending):
    """pending – колко заявки чакат този учител."""
    now = timezone.now()
    missions = missions_reviewed_by(teacher)
    open_count = missions.filter(is_active=True, deadline__gte=now).count()
    handover = unused_purchases(teacher).count()
    since = timezone.make_aware(datetime.combine(week_start_for(), time.min))
    approved = Claim.objects.filter(mission__in=missions, status=Claim.Status.APPROVED, reviewed_at__gte=since)
    students = approved.values("student").distinct().count()
    xp = XPTransaction.objects.filter(claim__in=approved).aggregate(total=Sum("amount"))["total"] or 0
    result = f"{approved.count()} потвърдени, {students} ученици, {xp} XP" if students else "още няма потвърдени"
    steps = [
        Step("Задай", count_text(open_count, "отворена мисия", "отворени мисии", "няма отворени мисии"), reverse("mission_list")),
        Step("Провери", count_text(pending, "чака решение", "чакат решение", "всичко е проверено"), reverse("review_list")),
        Step("Награди", count_text(handover, "за предаване", "за предаване", "нищо не чака"), reverse("purchase_list")),
        Step("Виж резултата", result, reverse("leaderboard") + "?period=week"),
    ]
    if pending:
        return Cycle(f"{count_text(pending, 'заявка чака', 'заявки чакат', '')} вашето решение.", steps=mark(steps, 1))
    if handover:
        return Cycle(f"{count_text(handover, 'награда чака', 'награди чакат', '')} да бъдат предадени."
                     if handover > 1 else "1 награда чака да бъде предадена.",
                     reverse("purchase_list"), "Към наградите", mark(steps, 2))
    if not open_count:
        return Cycle("Нямате отворена мисия. Задайте нова.", reverse("mission_create"), "Нова мисия", mark(steps, 0))
    return Cycle("Всичко е проверено. Ето какво стана тази седмица.", reverse("leaderboard") + "?period=week",
                 "Към класацията", mark(steps, 3))
