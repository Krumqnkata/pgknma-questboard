"""
Тестове за правилата на играта (раздел 3.1 на плана), вкл. всички гранични случаи:
двойно потвърждаване, седмичен лимит, пренасяне на остатъка, покупка без монети.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase

from accounts.testing import make_mission, make_student, make_teacher
from missions.models import Claim
from missions.services import GameRuleError

from .models import CoinTransaction, GameSettings, Level, Privilege, Purchase, XPTransaction
from .services import (
    approve_claim, award_xp, buy_privilege, coin_balance, level_for_xp, mark_purchase_used,
    reject_claim, student_stats, week_start_for, xp_total,
)

SOFIA = ZoneInfo("Europe/Sofia")
MONDAY = datetime(2026, 11, 16, 10, 0, tzinfo=SOFIA)     # понеделник
THURSDAY = datetime(2026, 11, 19, 10, 0, tzinfo=SOFIA)   # същата седмица
NEXT_MONDAY = datetime(2026, 11, 23, 9, 0, tzinfo=SOFIA)  # следващата седмица


class GameSettingsTests(TestCase):
    def test_default_rules_from_the_innovation(self):
        rules = GameSettings.load()
        self.assertEqual(rules.xp_per_coin, 50)
        self.assertEqual(rules.weekly_coin_limit, 5)

    def test_there_is_only_one_settings_row(self):
        GameSettings(xp_per_coin=40).save()
        GameSettings(xp_per_coin=60).save()
        self.assertEqual(GameSettings.objects.count(), 1)
        self.assertEqual(GameSettings.load().xp_per_coin, 60)


class InitialDataTests(TestCase):
    def test_levels_start_from_zero_xp(self):
        self.assertEqual(Level.objects.order_by("min_xp").first().min_xp, 0)

    def test_shop_has_deadline_pass_and_hint_token(self):
        codes = set(Privilege.objects.values_list("code", flat=True))
        self.assertTrue({"deadline_pass", "hint_token"} <= codes)


class WeekTests(TestCase):
    def test_week_starts_on_monday_by_default(self):
        self.assertEqual(week_start_for(THURSDAY), MONDAY.date())

    def test_week_start_day_comes_from_settings(self):
        rules = GameSettings.load()
        rules.week_start_day = GameSettings.Weekday.SUNDAY
        rules.save()
        self.assertEqual(week_start_for(THURSDAY), datetime(2026, 11, 15).date())


class CoinRulesTests(TestCase):
    """Курс 50 XP = 1 монета, най-много 5 монети на седмица."""

    def setUp(self):
        self.student = make_student()

    def award(self, xp, now=MONDAY):
        return award_xp(self.student, xp, reason="тест", now=now)

    def test_xp_is_converted_by_rate(self):
        self.assertEqual(self.award(120), 2)  # 120 XP → 2 монети, 20 XP остават
        self.assertEqual(coin_balance(self.student), 2)

    def test_remainder_adds_up_within_the_week(self):
        self.award(30)
        self.assertEqual(self.award(30, now=THURSDAY), 1)  # 30 + 30 = 60 → 1 монета

    def test_weekly_limit_gives_xp_but_no_more_coins(self):
        self.award(250)                                   # 5 монети – лимитът е достигнат
        self.assertEqual(self.award(100, now=THURSDAY), 0)
        self.assertEqual(coin_balance(self.student), 5)
        self.assertEqual(xp_total(self.student), 350)     # XP все пак се начислява

    def test_limit_resets_next_week(self):
        self.award(300)
        self.assertEqual(self.award(100, now=NEXT_MONDAY), 2)

    def test_remainder_carries_to_next_week(self):
        self.award(30)                                    # 0 монети, остават 30 XP
        self.assertEqual(self.award(20, now=NEXT_MONDAY), 1)

    def test_remainder_is_lost_when_carry_over_is_off(self):
        rules = GameSettings.load()
        rules.carry_over_remainder = False
        rules.save()
        self.award(30)
        self.assertEqual(self.award(20, now=NEXT_MONDAY), 0)

    def test_xp_above_the_limit_does_not_carry_over(self):
        self.award(400)                                   # 5 монети, 150 XP над лимита
        # Пренася се само остатъкът под курса: 150 % 50 = 0
        self.assertEqual(self.award(40, now=NEXT_MONDAY), 0)

    def test_rate_comes_from_settings(self):
        rules = GameSettings.load()
        rules.xp_per_coin = 20
        rules.save()
        self.assertEqual(self.award(60), 3)


class LevelTests(TestCase):
    def test_level_by_xp(self):
        # Примерни граници: 0, 100, 250, 500, 1000
        self.assertEqual(level_for_xp(0).number, 1)
        self.assertEqual(level_for_xp(99).number, 1)
        self.assertEqual(level_for_xp(100).number, 2)
        self.assertEqual(level_for_xp(5000).number, 5)

    def test_progress_to_next_level(self):
        student = make_student()
        award_xp(student, 175, reason="тест")
        stats = student_stats(student)
        self.assertEqual(stats.level.number, 2)
        self.assertEqual(stats.xp_to_next_level, 75)
        self.assertEqual(stats.progress_percent, 50)  # от 100 до 250, изминати 75 от 150


class ApproveClaimTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher, xp=60)
        self.claim = Claim.objects.create(mission=self.mission, student=self.student, evidence="готово")

    def test_xp_only_after_approval(self):
        self.assertEqual(xp_total(self.student), 0)
        result = approve_claim(self.claim, self.teacher)
        self.assertEqual(result.xp, 60)
        self.assertEqual(result.coins, 1)
        self.assertEqual(xp_total(self.student), 60)
        self.assertEqual(self.claim.status, Claim.Status.APPROVED)

    def test_double_approval_gives_xp_once(self):
        approve_claim(self.claim, self.teacher)
        with self.assertRaises(GameRuleError):
            approve_claim(self.claim, self.teacher)
        self.assertEqual(XPTransaction.objects.count(), 1)

    def test_rejected_claim_gives_nothing(self):
        reject_claim(self.claim, self.teacher, "Липсва доказателство")
        self.assertEqual(xp_total(self.student), 0)
        self.assertEqual(self.claim.review_comment, "Липсва доказателство")

    def test_cannot_approve_after_rejection(self):
        reject_claim(self.claim, self.teacher)
        with self.assertRaises(GameRuleError):
            approve_claim(self.claim, self.teacher)

    def test_only_mission_author_can_review(self):
        other_teacher = make_teacher("drug@example.com")
        with self.assertRaises(GameRuleError):
            approve_claim(self.claim, other_teacher)

    def test_student_cannot_approve(self):
        with self.assertRaises(GameRuleError):
            approve_claim(self.claim, self.student)

    def test_level_up_is_reported(self):
        award_xp(self.student, 50, reason="тест")   # 50 XP – ниво 1
        result = approve_claim(self.claim, self.teacher)  # +60 = 110 XP – ниво 2
        self.assertEqual(result.new_level.number, 2)

    def test_journal_records_who_and_why(self):
        approve_claim(self.claim, self.teacher)
        entry = XPTransaction.objects.get()
        self.assertEqual(entry.created_by, self.teacher)
        self.assertEqual(entry.claim, self.claim)
        self.assertIn(self.mission.title, entry.reason)


class ShopTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.hint = Privilege.objects.get(code="hint_token")  # 2 монети
        self.teacher = make_teacher()

    def give_coins(self, amount):
        CoinTransaction.objects.create(student=self.student, amount=amount,
                                       kind=CoinTransaction.Kind.CORRECTION, reason="тест")

    def test_buy_with_enough_coins(self):
        self.give_coins(3)
        purchase = buy_privilege(self.student, self.hint)
        self.assertEqual(purchase.price_paid, 2)
        self.assertEqual(coin_balance(self.student), 1)

    def test_buy_without_enough_coins(self):
        self.give_coins(1)
        with self.assertRaises(GameRuleError):
            buy_privilege(self.student, self.hint)
        self.assertEqual(Purchase.objects.count(), 0)

    def test_second_purchase_cannot_spend_the_same_coins(self):
        self.give_coins(2)
        buy_privilege(self.student, self.hint)
        with self.assertRaises(GameRuleError):
            buy_privilege(self.student, self.hint)
        self.assertEqual(coin_balance(self.student), 0)

    def test_inactive_privilege_cannot_be_bought(self):
        self.give_coins(10)
        self.hint.is_active = False
        self.hint.save()
        with self.assertRaises(GameRuleError):
            buy_privilege(self.student, self.hint)

    def test_price_paid_stays_after_price_change(self):
        self.give_coins(5)
        purchase = buy_privilege(self.student, self.hint)
        self.hint.price = 4
        self.hint.save()
        purchase.refresh_from_db()
        self.assertEqual(purchase.price_paid, 2)

    def test_teacher_marks_purchase_used_once(self):
        self.give_coins(2)
        topic = Privilege.objects.create(code="topic", name="Избор на тема", price=2)
        purchase = buy_privilege(self.student, topic)
        mark_purchase_used(purchase, self.teacher)
        self.assertTrue(purchase.is_used)
        with self.assertRaises(GameRuleError):
            mark_purchase_used(purchase, self.teacher)

    def test_student_cannot_mark_purchase_used(self):
        self.give_coins(2)
        purchase = buy_privilege(self.student, self.hint)
        with self.assertRaises(GameRuleError):
            mark_purchase_used(purchase, self.student)
