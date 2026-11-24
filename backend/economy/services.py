"""
Правилата на играта: XP, нива, монети, седмичен лимит и магазин (раздел 3.1).

Всяко начисляване и харчене минава само оттук. Страниците и API-то
викат тези функции и никога не пишат сами в таблиците с движения.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from badges.models import StudentBadge
from badges.services import award_badges
from missions.models import Claim
from missions.services import GameRuleError, claims_to_decide, missions_reviewed_by
from notifications.models import Notification
from notifications.services import notify

from .models import CoinTransaction, CoinWeek, GameSettings, Level, Privilege, Purchase, XPTransaction
from .words import coins_text

# ---------- Наличности (винаги се изчисляват от движенията) ----------


def xp_total(student):
    return student.xp_transactions.aggregate(total=Sum("amount"))["total"] or 0


def coin_balance(student):
    return student.coin_transactions.aggregate(total=Sum("amount"))["total"] or 0


def level_for_xp(xp):
    """Най-високото ниво, чиято граница е достигната."""
    return Level.objects.filter(min_xp__lte=xp).order_by("-min_xp").first()


def next_level_for_xp(xp):
    return Level.objects.filter(min_xp__gt=xp).order_by("min_xp").first()


@dataclass
class StudentStats:
    xp: int
    level: Level | None
    next_level: Level | None
    coins: int
    coins_this_week: int
    weekly_limit: int
    streak: int = 0  # поредни седмици с потвърдена мисия

    @property
    def progress_percent(self):
        """Колко процента от пътя до следващото ниво е изминат."""
        if not self.next_level:
            return 100
        start = self.level.min_xp if self.level else 0
        return int((self.xp - start) * 100 / (self.next_level.min_xp - start))

    @property
    def xp_to_next_level(self):
        return self.next_level.min_xp - self.xp if self.next_level else 0


def student_stats(student, now=None):
    xp = xp_total(student)
    week = CoinWeek.objects.filter(student=student, week_start=week_start_for(now)).first()
    return StudentStats(
        xp=xp,
        level=level_for_xp(xp),
        next_level=next_level_for_xp(xp),
        coins=coin_balance(student),
        coins_this_week=week.coins_earned if week else 0,
        weekly_limit=GameSettings.load().weekly_coin_limit,
        streak=streak_weeks(student, now),
    )


def streak_weeks(student, now=None):
    """
    Колко поредни седмици ученикът има поне една потвърдена мисия.
    Серията не се губи, докато текущата седмица не е свършила: ако тази
    седмица още няма мисия, се брои от миналата назад.
    """
    current = week_start_for(now)
    start_day = (current.weekday()) % 7
    reviewed = Claim.objects.filter(student=student, status=Claim.Status.APPROVED).values_list("reviewed_at", flat=True)
    weeks = set()
    for moment in reviewed:
        if moment:
            day = timezone.localdate(moment)
            weeks.add(day - timedelta(days=(day.weekday() - start_day) % 7))
    if current not in weeks:
        current -= timedelta(days=7)
    count = 0
    while current in weeks:
        count += 1
        current -= timedelta(days=7)
    return count


# ---------- Седмици и монети ----------


def week_start_for(now=None):
    """Датата, от която започва текущата седмица (денят се избира в настройките)."""
    today = timezone.localdate(now or timezone.now())
    start_day = GameSettings.load().week_start_day  # 0 = понеделник
    return today - timedelta(days=(today.weekday() - start_day) % 7)


def _current_week(student, rules, now):
    """
    Седмичната сметка на ученика, заключена до края на транзакцията.
    При нова седмица пренася остатъка от предишната, ако това е включено в настройките.
    """
    start = week_start_for(now)
    week = CoinWeek.objects.select_for_update().filter(student=student, week_start=start).first()
    if week:
        return week

    carry_in = 0
    previous = CoinWeek.objects.filter(student=student, week_start__lt=start).order_by("-week_start").first()
    if previous and rules.carry_over_remainder:
        # Пренася се само остатъкът под курса (напр. 30 от 50 XP).
        # XP над седмичния лимит не се пренася, иначе лимитът няма смисъл.
        carry_in = previous.xp_left % rules.xp_per_coin
    return CoinWeek.objects.create(student=student, week_start=start, carry_in=carry_in)


def award_xp(student, amount, reason, created_by=None, claim=None, now=None, is_bonus=False):
    """
    Начислява XP и превръща каквото може в монети по курса и седмичния лимит (Ф6).
    XP се пази винаги – дори когато лимитът е достигнат и монети не се дават.
    Връща колко монети са дадени.
    """
    rules = GameSettings.load()
    entry = XPTransaction.objects.create(student=student, amount=amount, reason=reason, claim=claim,
                                         created_by=created_by, is_bonus=is_bonus)

    week = _current_week(student, rules, now)
    week.xp_earned += amount

    coins_left_this_week = max(0, rules.weekly_coin_limit - week.coins_earned)
    new_coins = min(coins_left_this_week, week.xp_left // rules.xp_per_coin)

    week.coins_earned += new_coins
    week.xp_used += new_coins * rules.xp_per_coin
    week.save()

    if new_coins:
        CoinTransaction.objects.create(
            student=student, amount=new_coins, kind=CoinTransaction.Kind.EARNED,
            reason=f"{new_coins * rules.xp_per_coin} XP по курс {rules.xp_per_coin} XP = 1 монета",
            claim=claim, created_by=created_by,
        )
        entry.coins = new_coins
        entry.save(update_fields=["coins"])
    return new_coins


# ---------- Потвърждаване на заявки ----------


@dataclass
class ReviewResult:
    claim: Claim
    xp: int = 0
    coins: int = 0
    new_level: Level | None = None  # попълва се, ако ученикът е минал на ново ниво
    team: int = 0  # колко съотборници са получили същата награда


def _check_reviewer(claim, reviewer):
    # Заявката се проверява от автора на мисията, от избран от него заместник или от администратор.
    if not claim.mission.can_be_reviewed_by(reviewer):
        raise GameRuleError("Само учителят, създал мисията, и заместниците му могат да проверяват заявките по нея.")
    if claim.captain_id:
        raise GameRuleError("Заявката е част от отбор – решава се със заявката на капитана.")


def _mark_reviewed(claim, reviewer, status, comment):
    """
    Сменя състоянието САМО ако заявката още чака проверка.
    Ако двама натиснат едновременно (или един натисне два пъти), само първият минава.
    """
    updated = Claim.objects.filter(pk=claim.pk, status=Claim.Status.PENDING).update(
        status=status, reviewed_by=reviewer, reviewed_at=timezone.now(), review_comment=comment,
    )
    if updated == 0:
        raise GameRuleError("Тази заявка вече е проверена.")
    claim.refresh_from_db()


def approve_claim(claim, reviewer, comment="", now=None):
    """
    Учителят потвърждава заявка (Ф5): XP се начислява само сега.
    При отборна мисия същото решение важи за всички от отбора.
    """
    _check_reviewer(claim, reviewer)
    with transaction.atomic():
        result = _approve_one(claim, reviewer, comment, now)
        for member in _team_of(claim):
            _approve_one(member, reviewer, comment, now)
            result.team += 1
    return result


def _team_of(claim):
    return list(claim.team.filter(status=Claim.Status.PENDING).select_related("mission", "student"))


def _approve_one(claim, reviewer, comment, now):
    _mark_reviewed(claim, reviewer, Claim.Status.APPROVED, comment.strip())

    student = claim.student
    old_level = level_for_xp(xp_total(student))
    xp = claim.mission.xp
    what = "Домашна" if claim.mission.is_homework else "Мисия"
    coins = award_xp(student, xp, reason=f"{what} „{claim.mission.title}“",
                     created_by=reviewer, claim=claim, now=now)
    new_level = level_for_xp(xp_total(student))
    new_level = new_level if new_level != old_level else None

    # Известия за ученика (Ф15) и значки (Ф16) – в същата транзакция като XP
    text = f"Заявката за „{claim.mission.title}“ е потвърдена: +{xp} XP"
    if coins:
        text += f" и +{coins_text(coins)}"
    notify(student, Notification.Kind.CLAIM_APPROVED, text + "." + _teacher_says(claim),
           link=reverse("mission_detail", args=[claim.mission_id]))
    if new_level:
        notify(student, Notification.Kind.LEVEL_UP, f"Мина на {str(new_level).lower()}!", link=reverse("home"))
    _give_mission_rewards(claim, reviewer)
    award_badges(student)
    return ReviewResult(claim=claim, xp=xp, coins=coins, new_level=new_level)


def _give_mission_rewards(claim, reviewer):
    """Значката и предметът, които се печелят само от тази мисия."""
    mission, student = claim.mission, claim.student
    badge = mission.reward_badge
    if badge and badge.is_active:
        _, created = StudentBadge.objects.get_or_create(student=student, badge=badge, defaults={
            "given_by": reviewer, "claim": claim, "note": f"Мисия „{mission.title}“"[:200]})
        if created:
            notify(student, Notification.Kind.BADGE, f"Нова значка: „{badge.name}“ – {badge.description}",
                   link=reverse("profile"))
    if not mission.reward_item_id:
        return
    # Редът на предмета се заключва, за да не се раздадат повече бройки от наличните.
    item = Privilege.objects.select_for_update().get(pk=mission.reward_item_id)
    if item.is_cosmetic and student.purchases.filter(privilege=item).exists():
        return
    if item.is_sold_out:
        notify(student, Notification.Kind.CLAIM_APPROVED, f"Наградата „{item.name}“ вече е изчерпана.",
               link=reverse("mission_detail", args=[mission.pk]))
        return
    Purchase.objects.create(student=student, privilege=item, price_paid=0, claim=claim,
                            used_at=timezone.now() if item.is_cosmetic else None)
    if item.is_cosmetic:
        wear(student, item)
    notify(student, Notification.Kind.BONUS, f"Спечели „{item.name}“ от мисията „{mission.title}“!",
           link=reverse("profile" if item.is_cosmetic else "shop"))


def _take_mission_rewards(claim):
    """При отмяна: значката и предметът от мисията се връщат (освен ако предметът вече е предаден)."""
    claim.badges.all().delete()
    student = claim.student
    for purchase in claim.rewards.select_related("privilege"):
        item = purchase.privilege
        if not item.is_cosmetic and purchase.is_used:
            continue
        if item.is_cosmetic:
            field = "shown_title" if item.kind == Privilege.Kind.TITLE else "shown_frame"
            if getattr(student, f"{field}_id") == item.pk:
                wear(student, None, kind=item.kind)
        purchase.delete()


def _teacher_says(claim):
    return f" Учителят: „{claim.review_comment}“" if claim.review_comment else ""


def reject_claim(claim, reviewer, comment=""):
    """Учителят отказва заявка. Ученикът може да я подаде отново."""
    _check_reviewer(claim, reviewer)
    with transaction.atomic():
        for member in [claim, *_team_of(claim)]:
            _mark_reviewed(member, reviewer, Claim.Status.REJECTED, comment.strip())
            notify(member.student, Notification.Kind.CLAIM_REJECTED,
                   f"Заявката за „{claim.mission.title}“ е отказана.{_teacher_says(claim)} Можеш да я подадеш отново.",
                   link=reverse("mission_detail", args=[claim.mission_id]))
    return ReviewResult(claim=claim)


def pending_claims_for(reviewer):
    claims = claims_to_decide().select_related(
        "mission", "student", "student__school_class").prefetch_related("files", "team__student__school_class")
    if reviewer.is_admin_role:
        return claims
    return claims.filter(mission__in=missions_reviewed_by(reviewer))


# ---------- Бонус XP от учител ----------


def bonus_left_this_week(teacher, now=None):
    """Колко бонус XP може да даде още учителят тази седмица."""
    rules = GameSettings.load()
    since = timezone.make_aware(datetime.combine(week_start_for(now), time.min))
    given = XPTransaction.objects.filter(created_by=teacher, is_bonus=True, created_at__gte=since).aggregate(
        total=Sum("amount"))["total"] or 0
    return max(0, rules.bonus_weekly_xp - given)


def give_bonus(teacher, student, xp, reason, now=None):
    """
    Учителят дава бонус XP без мисия, напр. „Помощ при концерта“.
    Причината е задължителна, а лимитите са в „Настройки на играта“. XP минава
    през същите правила като при мисия: монети по курса и седмичния лимит,
    ново ниво, значки и известие до ученика.
    """
    rules = GameSettings.load()
    reason = (reason or "").strip()
    if not (teacher.is_teacher or teacher.is_admin_role):
        raise GameRuleError("Само учител може да дава бонус XP.")
    if not (student.is_student and student.is_active):
        raise GameRuleError("Бонус XP се дава само на ученици.")
    if not rules.bonus_max_xp:
        raise GameRuleError("Бонус XP е изключен от администратора.")
    if not 1 <= xp <= rules.bonus_max_xp:
        raise GameRuleError(f"Бонусът е от 1 до {rules.bonus_max_xp} XP.")
    if len(reason) < 3:
        raise GameRuleError("Напишете за какво е бонусът.")

    with transaction.atomic():
        User.objects.select_for_update().get(pk=teacher.pk)  # два бонуса наведнъж не минават лимита
        left = bonus_left_this_week(teacher, now)
        if xp > left:
            raise GameRuleError(f"Тази седмица можете да дадете още {left} бонус XP (лимит {rules.bonus_weekly_xp}).")
        old_level = level_for_xp(xp_total(student))
        coins = award_xp(student, xp, reason=f"Бонус: {reason[:200]}", created_by=teacher, now=now, is_bonus=True)
        new_level = level_for_xp(xp_total(student))
        text = f"Бонус +{xp} XP от {teacher.get_full_name() or 'учител'}"
        if coins:
            text += f" и +{coins_text(coins)}"
        notify(student, Notification.Kind.BONUS, f"{text}: {reason[:200]}", link=reverse("home"))
        if new_level != old_level and new_level:
            notify(student, Notification.Kind.LEVEL_UP, f"Мина на {str(new_level).lower()}!", link=reverse("home"))
        award_badges(student)
    return coins


# ---------- Отмяна на награда ----------
# Нищо не се изтрива: отмяната е ново движение с минус и причина, затова в
# журнала се вижда и наградата, и отмяната ѝ. Монетите, дадени заради това
# XP, също се връщат – ако вече са похарчени, сметката може да стане на минус
# и ученикът не може да пазарува, докато не спечели нови.


def can_undo(actor, given_by, given_at, now=None):
    """Администраторът – винаги; учителят – само своите награди и само няколко дни след това."""
    if actor.is_admin_role:
        return True
    if not actor.is_teacher or given_by != actor.pk:
        return False
    return (now or timezone.now()) - given_at <= timedelta(days=GameSettings.load().undo_days)


def _undo_xp(entry, actor, why, now=None):
    if hasattr(entry, "reversal"):
        raise GameRuleError("Тази награда вече е отменена.")
    if entry.amount <= 0 or entry.reverses_id:
        raise GameRuleError("Това движение не може да се отмени.")
    rules = GameSettings.load()
    XPTransaction.objects.create(
        student=entry.student, amount=-entry.amount, reason=f"Отменено: {entry.reason} ({why})"[:255],
        claim=entry.claim, created_by=actor, is_bonus=entry.is_bonus, reverses=entry,
    )
    if entry.coins:
        CoinTransaction.objects.create(
            student=entry.student, amount=-entry.coins, kind=CoinTransaction.Kind.CORRECTION,
            reason=f"Отменено: {entry.reason}"[:255], claim=entry.claim, created_by=actor,
        )
    # Ако наградата е от тази седмица, седмичната сметка се връща назад,
    # за да може ученикът пак да спечели тези монети.
    week = CoinWeek.objects.filter(student=entry.student, week_start=week_start_for(now)).first()
    if week and entry.created_at.date() >= week.week_start:
        week.xp_earned = max(0, week.xp_earned - entry.amount)
        week.coins_earned = max(0, week.coins_earned - entry.coins)
        week.xp_used = max(0, min(week.xp_used - entry.coins * rules.xp_per_coin, week.xp_earned + week.carry_in))
        week.save()


def _check_reason(why):
    why = (why or "").strip()
    if len(why) < 3:
        raise GameRuleError("Напишете защо отменяте.")
    return why[:200]


def undo_bonus(actor, entry, why, now=None):
    """Отменя бонус XP (и монетите от него)."""
    why = _check_reason(why)
    if not entry.is_bonus:
        raise GameRuleError("Това не е бонус.")
    if not can_undo(actor, entry.created_by_id, entry.created_at, now):
        raise GameRuleError("Можете да отмените само свой бонус, и то до "
                            f"{GameSettings.load().undo_days} дни след като сте го дали.")
    with transaction.atomic():
        User.objects.select_for_update().get(pk=entry.student_id)
        _undo_xp(entry, actor, why, now)
        notify(entry.student, Notification.Kind.UNDONE,
               f"Бонусът „{entry.reason.removeprefix('Бонус: ')}“ (+{entry.amount} XP) е отменен: {why}",
               link=reverse("home"))


def undo_approval(actor, claim, why, now=None):
    """
    Потвърдената заявка става отказана: XP и монетите се връщат, а ученикът
    вижда причината и може да подаде заявката отново, докато мисията е отворена.
    """
    why = _check_reason(why)
    if claim.status != Claim.Status.APPROVED:
        raise GameRuleError("Само потвърдена заявка може да се отмени.")
    allowed = actor.pk if claim.mission.can_be_reviewed_by(actor) else None
    if not can_undo(actor, allowed, claim.reviewed_at, now):
        raise GameRuleError("Можете да отмените само потвърждение по мисия, която проверявате, и то до "
                            f"{GameSettings.load().undo_days} дни след него.")
    with transaction.atomic():
        # При капитан се отменя за целия отбор, а при съотборник – само за него.
        team = claim.team.filter(status=Claim.Status.APPROVED).select_related("mission", "student")
        for member in [claim, *team]:
            User.objects.select_for_update().get(pk=member.student_id)
            for entry in member.xp_transactions.filter(amount__gt=0, reversal__isnull=True):
                _undo_xp(entry, actor, why, now)
            _take_mission_rewards(member)
            Claim.objects.filter(pk=member.pk).update(status=Claim.Status.REJECTED, reviewed_by=actor,
                                                      reviewed_at=timezone.now(), review_comment=why)
            notify(member.student, Notification.Kind.UNDONE,
                   f"Потвърждението на „{claim.mission.title}“ е отменено: {why}",
                   link=reverse("mission_detail", args=[claim.mission_id]))
        claim.refresh_from_db()
    return claim


# ---------- Магазин ----------


def is_unlocked(privilege, level):
    """Достатъчно ли е нивото за този предмет. Всеки предмет от ниво 1 е отключен."""
    return privilege.min_level <= 1 or (level is not None and level.number >= privilege.min_level)


def buy_privilege(student, privilege):
    """
    Ученикът купува привилегия с монети (Ф8).
    Редът на ученика се заключва, за да не минат две едновременни покупки
    с едни и същи монети.
    """
    if not student.is_student:
        raise GameRuleError("Само ученици могат да пазаруват.")
    if not privilege.is_active:
        raise GameRuleError("Тази привилегия вече не се продава.")
    if privilege.only_from_mission:
        raise GameRuleError(f"„{privilege.name}“ се печели само от мисия.")

    with transaction.atomic():
        User.objects.select_for_update().get(pk=student.pk)
        if not is_unlocked(privilege, level_for_xp(xp_total(student))):
            raise GameRuleError(f"„{privilege.name}“ се отключва на ниво {privilege.min_level}.")
        if privilege.stock is not None:
            # Заключва се и предметът – последната бройка се продава само веднъж.
            privilege = Privilege.objects.select_for_update().get(pk=privilege.pk)
            if privilege.is_sold_out:
                raise GameRuleError(f"„{privilege.name}“ е изчерпана.")
        if privilege.is_cosmetic and student.purchases.filter(privilege=privilege).exists():
            raise GameRuleError(f"Вече имаш „{privilege.name}“.")
        balance = coin_balance(student)
        if balance < privilege.price:
            raise GameRuleError(f"Нямаш достатъчно монети: нужни са {privilege.price}, имаш {balance}.")

        # Титлите и рамките не се отбелязват от учител – „използвани“ са веднага.
        purchase = Purchase.objects.create(student=student, privilege=privilege, price_paid=privilege.price,
                                           used_at=timezone.now() if privilege.is_cosmetic else None)
        CoinTransaction.objects.create(
            student=student, amount=-privilege.price, kind=CoinTransaction.Kind.SPENT,
            reason=f"Покупка: {privilege.name}", purchase=purchase, created_by=student,
        )
        if privilege.is_cosmetic:
            wear(student, privilege)  # новото се слага веднага
        award_badges(student)
    return purchase


def owned_cosmetics(student):
    """Титлите и рамките, които ученикът е купил или спечелил."""
    return Privilege.objects.filter(purchases__student=student).filter(
        kind__in=[Privilege.Kind.TITLE, Privilege.Kind.FRAME]).distinct()


def wear(student, privilege=None, kind=None):
    """
    Слага купена титла или рамка (или маха текущата, ако privilege е None).
    Може да се сложи само нещо, което ученикът е купил.
    """
    if privilege is not None:
        if not privilege.is_cosmetic or not owned_cosmetics(student).filter(pk=privilege.pk).exists():
            raise GameRuleError("Можеш да сложиш само титла или рамка, която си купил или спечелил.")
        kind = privilege.kind
    field = "shown_title" if kind == Privilege.Kind.TITLE else "shown_frame"
    setattr(student, field, privilege)
    student.save(update_fields=[field])


def mark_purchase_used(purchase, teacher, mission=None):
    """Учителят отбелязва, че ученикът е използвал привилегията (Ф9)."""
    if not (teacher.is_teacher or teacher.is_admin_role):
        raise GameRuleError("Само учител може да отбележи привилегия като използвана.")
    updated = Purchase.objects.filter(pk=purchase.pk, used_at__isnull=True).update(
        used_at=timezone.now(), marked_used_by=teacher, used_for_mission=mission,
    )
    if updated == 0:
        raise GameRuleError("Тази привилегия вече е използвана.")
    purchase.refresh_from_db()
    return purchase


def unused_purchases():
    """Неизползваните покупки, които учителят отбелязва. Hint Token се харчи сам – през асистента."""
    return Purchase.objects.filter(used_at__isnull=True, privilege__kind__in=[
        Privilege.Kind.PRIVILEGE, Privilege.Kind.SPONSOR]).exclude(
        privilege__code="hint_token").select_related(
        "student", "student__school_class", "privilege").order_by("purchased_at")


def active_privileges():
    """Каквото се продава в магазина. Предметите само от мисия не са тук."""
    return Privilege.objects.filter(is_active=True, only_from_mission=False).select_related("sponsor")
