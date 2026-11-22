"""Бонус XP и значки, които учителят дава ръчно."""
from django.test import TestCase
from django.urls import reverse

from accounts.testing import make_student, make_teacher
from badges.models import Badge, StudentBadge
from economy.models import GameSettings
from economy.services import bonus_left_this_week, coin_balance, give_bonus, xp_total
from missions.services import GameRuleError
from notifications.models import Notification


class BonusTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()

    def test_bonus_gives_xp_coins_and_notification(self):
        coins = give_bonus(self.teacher, self.student, 50, "Помощ при концерта")
        self.assertEqual(xp_total(self.student), 50)
        self.assertEqual((coins, coin_balance(self.student)), (1, 1))  # 50 XP = 1 монета
        note = self.student.notifications.get(kind=Notification.Kind.BONUS)
        self.assertIn("Бонус +50 XP", note.text)
        self.assertIn("Помощ при концерта", note.text)
        self.assertTrue(self.student.xp_transactions.get().is_bonus)

    def test_limits(self):
        with self.assertRaisesMessage(GameRuleError, "от 1 до 50 XP"):
            give_bonus(self.teacher, self.student, 51, "Много")
        with self.assertRaisesMessage(GameRuleError, "за какво"):
            give_bonus(self.teacher, self.student, 10, "  ")
        for _ in range(3):
            give_bonus(self.teacher, self.student, 50, "Седмица")
        self.assertEqual(bonus_left_this_week(self.teacher), 0)
        with self.assertRaisesMessage(GameRuleError, "още 0 бонус XP"):
            give_bonus(self.teacher, self.student, 1, "Още")
        # лимитът е на учител – друг учител може
        give_bonus(make_teacher("drug@example.com"), self.student, 10, "Друг учител")

    def test_weekly_coin_limit_still_applies(self):
        rules = GameSettings.load()
        rules.bonus_weekly_xp = 1000
        rules.save()
        for _ in range(8):
            give_bonus(self.teacher, self.student, 50, "Бонус")
        self.assertEqual(coin_balance(self.student), rules.weekly_coin_limit)  # 400 XP, но най-много 5 монети

    def test_only_teachers_give_and_only_students_get(self):
        with self.assertRaises(GameRuleError):
            give_bonus(self.student, make_student("b@example.com", nickname="Друг"), 10, "Аз на мен")
        with self.assertRaises(GameRuleError):
            give_bonus(self.teacher, make_teacher("t2@example.com"), 10, "На учител")

    def test_disabled_in_settings(self):
        rules = GameSettings.load()
        rules.bonus_max_xp = 0
        rules.save()
        with self.assertRaisesMessage(GameRuleError, "изключен"):
            give_bonus(self.teacher, self.student, 10, "Нещо")

    def test_bonus_can_level_up_and_is_celebrated(self):
        rules = GameSettings.load()
        rules.bonus_max_xp = 100
        rules.save()
        give_bonus(self.teacher, self.student, 100, "Отлична работа")  # 100 XP = ниво 2
        self.client.force_login(self.student)
        page = self.client.get(reverse("home"))
        self.assertContains(page, 'id="celebrate"')
        self.assertContains(page, "Бонус +100 XP")
        self.assertContains(page, "Мина на ниво 2")


class ManualBadgeTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.star = Badge.objects.get(name="Звезда на седмицата")

    def test_give_badge_once(self):
        from badges.services import give_badge

        give_badge(self.teacher, self.student, self.star, "Организира кампанията")
        award = StudentBadge.objects.get(student=self.student, badge=self.star)
        self.assertEqual((award.given_by, award.note), (self.teacher, "Организира кампанията"))
        self.assertIn("Организира кампанията", self.student.notifications.get(kind=Notification.Kind.BADGE).text)
        with self.assertRaisesMessage(GameRuleError, "вече има"):
            give_badge(self.teacher, self.student, self.star)

    def test_automatic_badges_cannot_be_given_by_hand(self):
        from badges.services import give_badge

        with self.assertRaisesMessage(GameRuleError, "не се дава ръчно"):
            give_badge(self.teacher, self.student, Badge.objects.get(name="Пет мисии"))

    def test_manual_badges_are_hidden_until_given(self):
        from badges.services import award_badges, badge_cards, give_badge

        self.assertEqual(award_badges(self.student), [])  # не се дават сами
        names = [card.badge.name for card in badge_cards(self.student)]
        self.assertNotIn("Звезда на седмицата", names)
        give_badge(self.teacher, self.student, self.star)
        self.assertIn("Звезда на седмицата", [card.badge.name for card in badge_cards(self.student)])


class RewardsPageTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.client.force_login(self.teacher)

    def test_page_and_menu(self):
        page = self.client.get(reverse("rewards"))
        self.assertContains(page, "Бонус XP")
        self.assertContains(page, "още <strong>150 XP</strong>", html=False)
        self.assertContains(page, "Звезда на седмицата")
        self.assertContains(self.client.get(reverse("review_list")), reverse("rewards"))

    def test_give_bonus_from_the_page(self):
        response = self.client.post(reverse("rewards"), {
            "action": "bonus", "student": self.student.pk, "xp": 30, "reason": "Помощ в библиотеката"}, follow=True)
        self.assertContains(response, "получи +30 XP")
        self.assertContains(response, "Помощ в библиотеката")
        self.assertEqual(xp_total(self.student), 30)

    def test_error_is_shown_on_the_form(self):
        response = self.client.post(reverse("rewards"), {
            "action": "bonus", "student": self.student.pk, "xp": 30, "reason": "x"})
        self.assertContains(response, "Напишете за какво е бонусът.")

    def test_give_badge_from_the_page(self):
        star = Badge.objects.get(name="Звезда на седмицата")
        response = self.client.post(reverse("rewards"), {
            "action": "badge", "student": self.student.pk, "badge": star.pk, "note": ""}, follow=True)
        self.assertContains(response, "получи значката")
        self.assertTrue(StudentBadge.objects.filter(student=self.student, badge=star).exists())

    def test_students_cannot_open_it(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("rewards")).status_code, 403)

    def test_api(self):
        response = self.client.post("/api/rewards/bonus/", {"student": self.student.pk, "xp": 20, "reason": "API"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["bonus_left"], 130)
        star = Badge.objects.get(name="Звезда на седмицата")
        response = self.client.post("/api/rewards/badge/", {"student": self.student.pk, "badge": star.pk},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post("/api/rewards/bonus/", {"student": self.student.pk, "xp": 5, "reason": "Аз"},
                                          content_type="application/json").status_code, 403)
