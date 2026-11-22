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
from badges.services import award_badges
from missions.models import Claim
from missions.services import GameRuleError
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
    XPTransaction.objects.create(student=student, amount=amount, reason=reason, claim=claim, created_by=created_by,
                                 is_bonus=is_bonus)

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
    return new_coins


# ---------- Потвърждаване на заявки ----------


@dataclass
class ReviewResult:
    claim: Claim
    xp: int = 0
    coins: int = 0
    new_level: Level | None = None  # попълва се, ако ученикът е минал на ново ниво


def _check_reviewer(claim, reviewer):
    # Заявката се проверява от автора на мисията (или администратор).
    if not (reviewer.is_admin_role or (reviewer.is_teacher and claim.mission.created_by_id == reviewer.id)):
        raise GameRuleError("Само учителят, създал мисията, може да проверява заявките по нея.")


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
    """Учителят потвърждава заявка (Ф5): XP се начислява само сега."""
    _check_reviewer(claim, reviewer)
    with transaction.atomic():
        _mark_reviewed(claim, reviewer, Claim.Status.APPROVED, comment.strip())

        student = claim.student
        old_level = level_for_xp(xp_total(student))
        xp = claim.mission.xp
        coins = award_xp(student, xp, reason=f"Мисия „{claim.mission.title}“",
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
        award_badges(student)

    return ReviewResult(claim=claim, xp=xp, coins=coins, new_level=new_level)


def _teacher_says(claim):
    return f" Учителят: „{claim.review_comment}“" if claim.review_comment else ""


def reject_claim(claim, reviewer, comment=""):
    """Учителят отказва заявка. Ученикът може да я подаде отново."""
    _check_reviewer(claim, reviewer)
    with transaction.atomic():
        _mark_reviewed(claim, reviewer, Claim.Status.REJECTED, comment.strip())
        notify(claim.student, Notification.Kind.CLAIM_REJECTED,
               f"Заявката за „{claim.mission.title}“ е отказана.{_teacher_says(claim)} Можеш да я подадеш отново.",
               link=reverse("mission_detail", args=[claim.mission_id]))
    return ReviewResult(claim=claim)


def pending_claims_for(reviewer):
    claims = Claim.objects.filter(status=Claim.Status.PENDING).select_related(
        "mission", "student", "student__school_class").prefetch_related("files")
    if reviewer.is_admin_role:
        return claims
    return claims.filter(mission__created_by=reviewer)


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


# ---------- Магазин ----------


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

    with transaction.atomic():
        User.objects.select_for_update().get(pk=student.pk)
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
    """Титлите и рамките, които ученикът е купил."""
    return Privilege.objects.filter(purchases__student=student).exclude(kind=Privilege.Kind.PRIVILEGE).distinct()


def wear(student, privilege=None, kind=None):
    """
    Слага купена титла или рамка (или маха текущата, ако privilege е None).
    Може да се сложи само нещо, което ученикът е купил.
    """
    if privilege is not None:
        if not privilege.is_cosmetic or not owned_cosmetics(student).filter(pk=privilege.pk).exists():
            raise GameRuleError("Можеш да сложиш само титла или рамка, която си купил.")
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
    return Purchase.objects.filter(used_at__isnull=True, privilege__kind=Privilege.Kind.PRIVILEGE).exclude(
        privilege__code="hint_token").select_related(
        "student", "student__school_class", "privilege").order_by("purchased_at")


def active_privileges():
    return Privilege.objects.filter(is_active=True)
