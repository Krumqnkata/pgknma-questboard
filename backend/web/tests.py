"""Тестове на страниците: кой какво може да отвори и направи."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild
from accounts.testing import make_mission, make_student, make_teacher
from missions.models import Claim, Mission


class MissionPageTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher, title="Помощ в библиотеката")

    def mission_form_data(self, **fields):
        data = {
            "title": "Нова мисия", "description": "Описание", "criteria": "Критерий",
            "guild": Guild.objects.get(name="Explorers").pk, "xp": 40,
            "deadline": (timezone.localtime() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            "hints_allowed": "on",
        }
        data.update(fields)
        return data

    # --- Учител ---

    def test_teacher_creates_mission(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission_create"), self.mission_form_data())
        mission = Mission.objects.get(title="Нова мисия")
        self.assertRedirects(response, reverse("mission_detail", args=[mission.pk]))
        self.assertEqual(mission.created_by, self.teacher)

    def test_form_shows_error_for_too_much_xp(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission_create"), self.mission_form_data(xp=500))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Най-много 100 XP")
        self.assertFalse(Mission.objects.filter(title="Нова мисия").exists())

    def test_teacher_cannot_edit_another_teachers_mission(self):
        other = make_teacher("drug@example.com")
        self.client.force_login(other)
        response = self.client.get(reverse("mission_edit", args=[self.mission.pk]))
        self.assertEqual(response.status_code, 404)

    def test_teacher_sees_claims_on_own_mission(self):
        Claim.objects.create(mission=self.mission, student=self.student, evidence="https://example.com")
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("mission_detail", args=[self.mission.pk]))
        self.assertContains(response, "https://example.com")

    # --- Ученик ---

    def test_student_cannot_open_create_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("mission_create"))
        self.assertEqual(response.status_code, 403)

    def test_student_sees_active_missions(self):
        make_mission(self.teacher, title="Спряна мисия", is_active=False)
        self.client.force_login(self.student)
        response = self.client.get(reverse("mission_list"))
        self.assertContains(response, "Помощ в библиотеката")
        self.assertNotContains(response, "Спряна мисия")

    def test_student_submits_claim(self):
        self.client.force_login(self.student)
        url = reverse("mission_detail", args=[self.mission.pk])
        response = self.client.post(url, {"evidence": "Помагах 2 часа"}, follow=True)
        self.assertContains(response, "Заявката е изпратена")
        self.assertTrue(Claim.objects.filter(mission=self.mission, student=self.student).exists())

    def test_second_claim_shows_error(self):
        Claim.objects.create(mission=self.mission, student=self.student, evidence="първи")
        self.client.force_login(self.student)
        url = reverse("mission_detail", args=[self.mission.pk])
        response = self.client.post(url, {"evidence": "втори"}, follow=True)
        self.assertContains(response, "Вече имате заявка")

    def test_student_cannot_open_stopped_mission_without_claim(self):
        stopped = make_mission(self.teacher, title="Спряна", is_active=False)
        self.client.force_login(self.student)
        response = self.client.get(reverse("mission_detail", args=[stopped.pk]))
        self.assertEqual(response.status_code, 404)

    # --- Начална страница ---

    def test_home_sends_each_role_to_its_page(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("home")), reverse("mission_list"))
