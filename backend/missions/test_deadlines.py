"""„Удължен срок“ и времето за поправяне на върната заявка."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolClass
from accounts.testing import make_mission, make_student, make_teacher
from economy.models import GameSettings, Privilege, Purchase
from economy.services import approve_claim, mark_purchase_used, reject_claim, unused_purchases
from missions.deadlines import can_submit, deadline_for, missions_to_extend, unused_passes, use_pass, why_not_extend
from missions.models import Claim, DeadlineExtension, Mission
from missions.services import GameRuleError, missions_for_student, submit_claim
from questboard.diagnostics import expired_missions
from web.cycle import student_cycle
from economy.services import student_stats


class Base(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.other = make_student("drug@example.com", "Комета")
        self.mission = make_mission(self.teacher, title="Плакат")

    def give_pass(self, student=None):
        return Purchase.objects.create(student=student or self.student, privilege=Privilege.objects.get(code="deadline_pass"),
                                       price_paid=3)

    def move_deadline(self, **delta):
        self.mission.deadline = timezone.now() + timedelta(**delta)
        self.mission.save()


class ExtensionTests(Base):
    def test_moves_the_deadline_only_for_this_student(self):
        purchase = self.give_pass()
        deadline = self.mission.deadline
        use_pass(self.student, self.mission)
        self.assertEqual(deadline_for(self.student, self.mission), deadline + timedelta(days=3))
        self.assertEqual(deadline_for(self.other, self.mission), deadline)
        purchase.refresh_from_db()
        self.assertEqual((purchase.is_used, purchase.used_for_mission), (True, self.mission))
        self.move_deadline(hours=-1)  # срокът мина: той още може, другият не
        submit_claim(self.student, self.mission, "Готово")
        with self.assertRaises(GameRuleError):
            submit_claim(self.other, self.mission, "Готово")

    def test_works_shortly_after_the_deadline(self):
        self.give_pass()
        self.move_deadline(days=-1)
        self.assertFalse(can_submit(self.student, self.mission))
        self.assertIn(self.mission, missions_to_extend(self.student))
        self.assertNotIn(self.mission, missions_for_student(self.student))
        use_pass(self.student, self.mission)
        self.assertTrue(can_submit(self.student, self.mission))
        self.assertIn(self.mission, missions_for_student(self.student))
        self.assertNotIn(self.mission, missions_for_student(self.other))
        self.assertNotIn(self.mission, missions_for_student())

    def test_too_late(self):
        self.give_pass()
        self.move_deadline(days=-3)
        self.assertIn("най-късно 2 дни", why_not_extend(self.student, self.mission))
        with self.assertRaises(GameRuleError):
            use_pass(self.student, self.mission)
        self.assertEqual(unused_passes(self.student).count(), 1)  # не е похарчен

    def test_once_per_mission(self):
        self.give_pass()
        self.give_pass()
        use_pass(self.student, self.mission)
        with self.assertRaisesMessage(GameRuleError, "само веднъж"):
            use_pass(self.student, self.mission)
        self.assertEqual(unused_passes(self.student).count(), 1)

    def test_teacher_can_forbid_it(self):
        self.give_pass()
        self.mission.extensions_allowed = False
        self.mission.save()
        with self.assertRaisesMessage(GameRuleError, "не се удължава"):
            use_pass(self.student, self.mission)

    def test_refused_without_a_pass_after_a_claim_and_for_a_stopped_mission(self):
        with self.assertRaisesMessage(GameRuleError, "Нямаш"):
            use_pass(self.student, self.mission)
        self.give_pass()
        submit_claim(self.student, self.mission, "Готово")
        with self.assertRaisesMessage(GameRuleError, "Вече си подал"):
            use_pass(self.student, self.mission)
        self.mission.is_active = False
        self.mission.save()
        self.assertIn("не приема", why_not_extend(self.other, self.mission))

    def test_foreign_homework(self):
        homework = make_mission(self.teacher, guild=None, kind=Mission.Kind.HOMEWORK, subject="Физика", xp=10)
        homework.school_classes.add(SchoolClass.objects.create(name="8Я"))
        self.give_pass()
        with self.assertRaises(GameRuleError):
            use_pass(self.student, homework)

    def test_captain_extends_for_the_team(self):
        self.mission.is_group = True
        self.mission.save()
        self.give_pass()
        use_pass(self.student, self.mission)
        self.move_deadline(hours=-1)
        claim = submit_claim(self.student, self.mission, "Готово", teammates=["Комета"])
        self.assertEqual(claim.team.count(), 1)

    def test_later_deadline_for_everyone_wins(self):
        self.give_pass()
        use_pass(self.student, self.mission)
        self.move_deadline(days=60)
        self.assertEqual(deadline_for(self.student, self.mission), self.mission.deadline)

    def test_students_use_it_themselves(self):
        purchase = self.give_pass()
        self.assertNotIn(purchase, unused_purchases(self.teacher))
        with self.assertRaises(GameRuleError):
            mark_purchase_used(purchase, self.teacher)

    def test_strange_settings_still_give_a_day(self):
        rules = GameSettings.load()
        rules.extension_days, rules.extension_late_days = 1, 5
        rules.save()
        self.give_pass()
        self.move_deadline(days=-4)
        self.assertGreater(use_pass(self.student, self.mission).until, timezone.now() + timedelta(hours=23))


class ResubmitTests(Base):
    def reject(self):
        claim = submit_claim(self.student, self.mission, "Готово")
        reject_claim(claim, self.teacher, "Липсва снимка")
        return claim

    def test_returned_claim_can_be_fixed_after_the_deadline(self):
        claim = self.reject()
        self.move_deadline(hours=-5)
        submit_claim(self.student, self.mission, "Готово със снимка")
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.Status.PENDING)
        approve_claim(claim, self.teacher)

    def test_but_not_forever(self):
        claim = self.reject()
        self.move_deadline(days=-9)
        Claim.objects.filter(pk=claim.pk).update(reviewed_at=timezone.now() - timedelta(days=3))
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "Късно")

    def test_next_step_still_shows_it(self):
        self.reject()
        self.move_deadline(hours=-5)
        cycle = student_cycle(self.student, student_stats(self.student), [])
        self.assertIn("е върната", cycle.headline)

    def test_system_check_waits_for_students_with_time(self):
        self.reject()
        self.move_deadline(days=-3)
        self.assertNotIn(self.mission, expired_missions())
        Claim.objects.update(reviewed_at=timezone.now() - timedelta(days=3))
        self.assertIn(self.mission, expired_missions())
        DeadlineExtension.objects.create(mission=self.mission, student=self.other, until=timezone.now() + timedelta(days=1))
        self.assertNotIn(self.mission, expired_missions())


class PageTests(Base):
    def test_button_and_marks(self):
        self.client.force_login(self.student)
        url = reverse("mission_detail", args=[self.mission.pk])
        self.assertContains(self.client.get(url), "Вземи го от магазина")
        self.give_pass()
        self.assertContains(self.client.get(url), "Използвай „Удължен срок“")
        page = self.client.post(reverse("mission_extend", args=[self.mission.pk]), follow=True)
        self.assertContains(page, "Срокът ти вече е до")
        self.assertContains(page, "за теб:")
        self.assertContains(self.client.get(reverse("mission_list")), "Удължен срок")
        self.client.post(url, {"evidence": "Готово"})
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("review_list")), "удължен срок")
        self.assertContains(self.client.get(url), "удължен срок")
        self.assertEqual(self.client.post(reverse("mission_extend", args=[self.mission.pk])).status_code, 403)

    def test_recently_expired_are_listed_only_with_a_pass(self):
        self.move_deadline(hours=-3)
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse("mission_list")), "Срокът току-що мина")
        self.give_pass()
        self.assertContains(self.client.get(reverse("mission_list")), "Срокът току-що мина")
        self.assertContains(self.client.get(reverse("mission_detail", args=[self.mission.pk])), "още можеш да го удължиш")

    def test_buying_says_how_to_use_it(self):
        from economy.models import CoinTransaction

        CoinTransaction.objects.create(student=self.student, amount=5, kind="earned", reason="тест")
        self.client.force_login(self.student)
        privilege = Privilege.objects.get(code="deadline_pass")
        self.assertContains(self.client.post(reverse("shop_buy", args=[privilege.pk]), follow=True), "Използва се от страницата")
