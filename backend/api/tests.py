from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild, User
from accounts.testing import make_mission, make_student, make_teacher
from missions.models import Claim


class ApiTests(TestCase):
    def test_health_is_public(self):
        response = self.client.get(reverse("api-health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_me_requires_login(self):
        response = self.client.get(reverse("api-me"))
        self.assertEqual(response.status_code, 403)

    def test_me_returns_role(self):
        user = User.objects.create_user("t@example.com", "TaynaParola123", role=User.Role.TEACHER)
        self.client.force_login(user)
        response = self.client.get(reverse("api-me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "teacher")


class MissionApiTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher)

    def mission_data(self, **fields):
        data = {
            "title": "API мисия", "description": "Описание", "criteria": "Критерий",
            "guild": Guild.objects.get(name="Citizens").pk, "xp": 30,
            "deadline": (timezone.now() + timedelta(days=3)).isoformat(),
        }
        data.update(fields)
        return data

    def test_teacher_creates_mission(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission-list"), self.mission_data(), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["created_by"], str(self.teacher))

    def test_api_uses_the_same_xp_limit(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission-list"), self.mission_data(xp=999),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("xp", response.json())

    def test_student_cannot_create_mission(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("mission-list"), self.mission_data(), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_teacher_lists_only_own_missions(self):
        make_mission(make_teacher("drug@example.com"), title="Чужда")
        self.client.force_login(self.teacher)
        titles = [m["title"] for m in self.client.get(reverse("mission-list")).json()]
        self.assertEqual(titles, [self.mission.title])

    def test_teacher_cannot_change_another_teachers_mission(self):
        self.client.force_login(make_teacher("drug@example.com"))
        response = self.client.patch(reverse("mission-detail", args=[self.mission.pk]), {"xp": 10},
                                     content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_student_claims_through_api(self):
        self.client.force_login(self.student)
        url = reverse("mission-claim", args=[self.mission.pk])
        first = self.client.post(url, {"evidence": "готово"}, content_type="application/json")
        second = self.client.post(url, {"evidence": "пак"}, content_type="application/json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Claim.objects.count(), 1)

    def test_student_sees_only_own_claims(self):
        other = make_student("drug@example.com", nickname="Сокол")
        Claim.objects.create(mission=self.mission, student=other, evidence="чуждо")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("claim-list")).json(), [])
