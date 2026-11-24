from django.test import TestCase
from django.urls import reverse

from accounts.models import Guild, User
from accounts.testing import make_mission, make_student, make_teacher
from economy.models import CoinTransaction, Privilege
from economy.services import approve_claim, buy_privilege
from missions.services import submit_claim
from notifications.models import Notification

from .models import Badge, StudentBadge
from .services import award_badges, badge_cards


class BadgeTests(TestCase):
    """Значки за постижения (Ф16). Началните значки идват от миграцията."""

    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.missions_made = 0

    def complete(self, count, guild="Техничари", xp=10):
        for _ in range(count):
            self.missions_made += 1
            mission = make_mission(self.teacher, title=f"Мисия {self.missions_made}", xp=xp,
                                   guild=Guild.objects.get(name=guild))
            approve_claim(submit_claim(self.student, mission, "Готово, ето доказателството."), self.teacher)

    def earned(self):
        return set(self.student.badges.values_list("badge__name", flat=True))

    def test_first_mission_badge_and_notification(self):
        self.complete(1)
        self.assertEqual(self.earned(), {"Първа мисия"})
        note = self.student.notifications.get(kind=Notification.Kind.BADGE)
        self.assertIn("„Първа мисия“", note.text)

    def test_five_missions_in_one_guild(self):
        self.complete(4, guild="Техничари")
        self.complete(1, guild="Изследователи")
        self.assertIn("Пет мисии", self.earned())
        self.assertNotIn("Верен на гилдията", self.earned())  # 4 + 1 в различни гилдии
        self.complete(1, guild="Техничари")
        self.assertIn("Верен на гилдията", self.earned())

    def test_badge_for_a_specific_guild(self):
        Badge.objects.create(name="Изследовател", description="3 мисии на Изследователи", rule=Badge.Rule.GUILD_MISSIONS,
                             threshold=3, guild=Guild.objects.get(name="Изследователи"))
        self.complete(3, guild="Техничари")
        self.assertNotIn("Изследовател", self.earned())
        self.complete(3, guild="Изследователи")
        self.assertIn("Изследовател", self.earned())

    def test_level_badge(self):
        self.complete(1, xp=100)
        self.assertNotIn("Майстор", self.earned())
        self.complete(2, xp=100)  # 300 XP – ниво 3 започва от 250
        self.assertIn("Майстор", self.earned())

    def test_purchase_badge(self):
        CoinTransaction.objects.create(student=self.student, amount=5, kind=CoinTransaction.Kind.EARNED, reason="тест")
        buy_privilege(self.student, Privilege.objects.get(code="deadline_pass"))
        self.assertIn("Пръв в магазина", self.earned())

    def test_badge_is_given_only_once(self):
        self.complete(2)
        self.assertEqual(StudentBadge.objects.filter(student=self.student, badge__name="Първа мисия").count(), 1)
        self.assertEqual(award_badges(self.student), [])

    def test_inactive_badges_are_not_given_or_shown(self):
        Badge.objects.filter(name="Първа мисия").update(is_active=False)
        self.complete(1)
        self.assertNotIn("Първа мисия", self.earned())
        self.assertNotIn("Първа мисия", [card.badge.name for card in badge_cards(self.student)])

    def test_new_badge_can_be_given_to_those_who_already_earned_it(self):
        self.complete(2)
        badge = Badge.objects.create(name="Две мисии", description="2 мисии", rule=Badge.Rule.MISSIONS, threshold=2)
        self.assertEqual(award_badges(self.student), [badge])

    def test_progress_cards(self):
        self.complete(3)
        cards = {card.badge.name: card for card in badge_cards(self.student)}
        self.assertTrue(cards["Първа мисия"].earned)
        self.assertEqual((cards["Пет мисии"].value, cards["Пет мисии"].percent), (3, 60))
        self.assertFalse(cards["Пет мисии"].earned)

    def test_home_profile_and_api(self):
        self.complete(1)
        self.client.force_login(self.student)
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Значки")
        self.assertContains(home, "1 от 5")  # напредък към „Пет мисии“
        self.assertContains(self.client.get(reverse("profile")), "Първа мисия")
        data = self.client.get("/api/me/badges/").json()
        self.assertTrue(next(item for item in data if item["name"] == "Първа мисия")["earned"])

    def test_admin_can_award_new_badges_to_everyone(self):
        self.complete(2)
        badge = Badge.objects.create(name="Две мисии", description="2 мисии", rule=Badge.Rule.MISSIONS, threshold=2)
        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        response = self.client.post(reverse("admin:badges_badge_changelist"),
                                    {"action": "award_to_everyone", "_selected_action": [badge.pk]}, follow=True)
        self.assertContains(response, "Раздадени значки: 1.")
        self.assertIn("Две мисии", self.earned())
