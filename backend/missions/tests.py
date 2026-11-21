"""Тестове за правилата на мисиите и граничните случаи от раздел 3.1 на плана."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Guild
from accounts.testing import make_mission, make_student, make_teacher
from economy.models import GameSettings

from .models import Claim, Mission
from .services import GameRuleError, missions_for_student, submit_claim


class MissionRulesTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()

    def new_mission(self, **fields):
        data = {
            "title": "Мисия", "description": "Описание", "criteria": "Критерий", "xp": 50,
            "guild": Guild.objects.get(name="Builders"), "created_by": self.teacher,
            "deadline": timezone.now() + timedelta(days=3),
        }
        data.update(fields)
        return Mission(**data)

    def test_valid_mission(self):
        self.new_mission().full_clean()

    def test_xp_above_the_limit_is_rejected(self):
        with self.assertRaises(ValidationError) as error:
            self.new_mission(xp=101).full_clean()
        self.assertIn("xp", error.exception.message_dict)

    def test_limit_comes_from_admin_settings(self):
        settings = GameSettings.load()
        settings.max_xp_per_mission = 200
        settings.save()
        self.new_mission(xp=150).full_clean()

    def test_new_mission_cannot_have_past_deadline(self):
        with self.assertRaises(ValidationError) as error:
            self.new_mission(deadline=timezone.now() - timedelta(hours=1)).full_clean()
        self.assertIn("deadline", error.exception.message_dict)


class SubmitClaimTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher)

    def test_student_submits_claim(self):
        claim = submit_claim(self.student, self.mission, "https://example.com/rabota")
        self.assertEqual(claim.status, Claim.Status.PENDING)

    def test_same_mission_twice_is_rejected(self):
        submit_claim(self.student, self.mission, "първи път")
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "втори път")
        self.assertEqual(Claim.objects.count(), 1)

    def test_claim_after_deadline_is_rejected(self):
        Mission.objects.filter(pk=self.mission.pk).update(deadline=timezone.now() - timedelta(minutes=1))
        self.mission.refresh_from_db()
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "закъснях")

    def test_claim_for_stopped_mission_is_rejected(self):
        self.mission.is_active = False
        self.mission.save()
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "доказателство")

    def test_teacher_cannot_claim(self):
        with self.assertRaises(GameRuleError):
            submit_claim(self.teacher, self.mission, "доказателство")

    def test_empty_evidence_is_rejected(self):
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "   ")

    def test_rejected_claim_can_be_submitted_again(self):
        claim = submit_claim(self.student, self.mission, "първи опит")
        claim.status = Claim.Status.REJECTED
        claim.review_comment = "Липсва връзка"
        claim.save()

        again = submit_claim(self.student, self.mission, "втори опит с връзка")
        self.assertEqual(again.pk, claim.pk)
        self.assertEqual(again.status, Claim.Status.PENDING)
        self.assertEqual(again.review_comment, "")

    def test_approved_claim_cannot_be_submitted_again(self):
        claim = submit_claim(self.student, self.mission, "готово")
        claim.status = Claim.Status.APPROVED
        claim.save()
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.mission, "пак")


class StudentVisibilityTests(TestCase):
    def test_student_sees_only_active_missions_with_open_deadline(self):
        teacher = make_teacher()
        open_mission = make_mission(teacher, title="Отворена")
        make_mission(teacher, title="Спряна", is_active=False)
        expired = make_mission(teacher, title="Изтекла")
        Mission.objects.filter(pk=expired.pk).update(deadline=timezone.now() - timedelta(days=1))

        self.assertEqual(list(missions_for_student()), [open_mission])
