"""Отмяна на награди: бонус XP, потвърдена заявка и значка, дадена ръчно."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.testing import make_mission, make_student, make_teacher
from badges.models import Badge, StudentBadge
from badges.services import give_badge, take_badge
from economy.models import CoinWeek, XPTransaction
from economy.services import (
    approve_claim, coin_balance, give_bonus, student_stats, undo_approval, undo_bonus, week_start_for, xp_total,
)
from missions.models import Claim
from missions.services import GameRuleError, submit_claim
from notifications.models import Notification


class UndoBonusTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        give_bonus(self.teacher, self.student, 50, "Помощ при концерта")
        self.entry = XPTransaction.objects.get(is_bonus=True)

    def test_xp_and_coins_go_back_and_history_stays(self):
        self.assertEqual((xp_total(self.student), coin_balance(self.student), self.entry.coins), (50, 1, 1))
        undo_bonus(self.teacher, self.entry, "Беше за друг ученик")
        self.assertEqual((xp_total(self.student), coin_balance(self.student)), (0, 0))
        self.assertEqual(XPTransaction.objects.count(), 2)  # нищо не е изтрито – има движение с минус
        self.assertIn("Беше за друг ученик",
                      self.student.notifications.get(kind=Notification.Kind.UNDONE).text)
        week = CoinWeek.objects.get(student=self.student, week_start=week_start_for())
        self.assertEqual((week.xp_earned, week.coins_earned), (0, 0))  # монетите могат да се спечелят пак

    def test_only_once_and_reason_required(self):
        with self.assertRaisesMessage(GameRuleError, "защо"):
            undo_bonus(self.teacher, self.entry, "")
        undo_bonus(self.teacher, self.entry, "Грешка")
        self.entry.refresh_from_db()
        with self.assertRaisesMessage(GameRuleError, "вече е отменена"):
            undo_bonus(self.teacher, self.entry, "Пак")

    def test_who_and_until_when(self):
        with self.assertRaises(GameRuleError):
            undo_bonus(make_teacher("drug@example.com"), self.entry, "Не е мой")
        XPTransaction.objects.filter(pk=self.entry.pk).update(created_at=timezone.now() - timedelta(days=8))
        self.entry.refresh_from_db()
        with self.assertRaisesMessage(GameRuleError, "до 7 дни"):
            undo_bonus(self.teacher, self.entry, "Късно")
        admin = User.objects.create_superuser("a@example.com", "TaynaParola123")
        undo_bonus(admin, self.entry, "Администраторът може винаги")
        self.assertEqual(xp_total(self.student), 0)

    def test_spent_coins_make_the_balance_negative(self):
        from economy.models import Privilege
        from economy.services import buy_privilege

        give_bonus(self.teacher, self.student, 50, "Още")
        buy_privilege(self.student, Privilege.objects.get(code="hint_token"))  # 2 монети
        undo_bonus(self.teacher, self.entry, "Грешка")
        self.assertEqual(coin_balance(self.student), -1)


class UndoApprovalTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.mission = make_mission(self.teacher, xp=100)
        self.claim = submit_claim(self.student, self.mission, "Готово, ето доказателството.")
        approve_claim(self.claim, self.teacher)

    def test_approval_becomes_rejection_and_can_be_resubmitted(self):
        self.assertEqual(student_stats(self.student).level.number, 2)
        undo_approval(self.teacher, self.claim, "Снимката е от миналата година")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.REJECTED)
        self.assertEqual(self.claim.review_comment, "Снимката е от миналата година")
        self.assertEqual(xp_total(self.student), 0)
        self.assertEqual(student_stats(self.student).level.number, 1)
        submit_claim(self.student, self.mission, "Ето новата снимка.")  # може да опита пак

    def test_only_approved_and_own_missions(self):
        with self.assertRaises(GameRuleError):
            undo_approval(make_teacher("drug@example.com"), self.claim, "Не е моя")
        undo_approval(self.teacher, self.claim, "Грешка")
        self.claim.refresh_from_db()
        with self.assertRaisesMessage(GameRuleError, "Само потвърдена"):
            undo_approval(self.teacher, self.claim, "Пак")

    def test_undo_button_on_mission_page(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("mission_detail", args=[self.mission.pk]))
        self.assertContains(page, reverse("claim_undo", args=[self.claim.pk]))
        response = self.client.post(reverse("claim_undo", args=[self.claim.pk]), {"why": "Грешна заявка"}, follow=True)
        self.assertContains(response, "Потвърждението за")
        self.assertEqual(xp_total(self.student), 0)


class TakeBadgeTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.award = give_badge(self.teacher, self.student, Badge.objects.get(name="Звезда на седмицата"))

    def test_take_back(self):
        take_badge(self.teacher, self.award, "Беше за друг ученик")
        self.assertFalse(StudentBadge.objects.filter(pk=self.award.pk).exists())
        self.assertIn("отнета", self.student.notifications.get(kind=Notification.Kind.UNDONE).text)

    def test_automatic_badges_stay(self):
        automatic = StudentBadge.objects.create(student=self.student, badge=Badge.objects.get(name="Първа мисия"))
        with self.assertRaisesMessage(GameRuleError, "дадени от учител"):
            take_badge(self.teacher, automatic, "Не може")


class RewardsPageUndoTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.client.force_login(self.teacher)
        give_bonus(self.teacher, self.student, 30, "Помощ")
        self.entry = XPTransaction.objects.get(is_bonus=True)

    def test_undo_from_rewards_page(self):
        page = self.client.get(reverse("rewards"))
        self.assertContains(page, "Отмени")
        response = self.client.post(reverse("rewards"), {"action": "undo_bonus", "id": self.entry.pk,
                                                         "why": "Грешен ученик"}, follow=True)
        self.assertContains(response, "е отменен")
        self.assertContains(response, "отменен</span>", html=False)
        self.assertEqual(xp_total(self.student), 0)

    def test_admin_action(self):
        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        response = self.client.post(reverse("admin:economy_xptransaction_changelist"),
                                    {"action": "undo_selected", "_selected_action": [self.entry.pk]}, follow=True)
        self.assertContains(response, "Отменени: 1.")
        self.assertEqual(xp_total(self.student), 0)
