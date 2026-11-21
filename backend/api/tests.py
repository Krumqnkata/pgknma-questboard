from django.test import TestCase
from django.urls import reverse

from accounts.models import User


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
