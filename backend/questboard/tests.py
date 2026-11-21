"""Проверява, че всяка страница в менюто на администрацията се отваря без грешка."""
from django.conf import settings
from django.test import TestCase

from accounts.models import User


class AdminMenuTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@example.com", "TaynaParola123")

    def menu_links(self):
        for group in settings.UNFOLD["SIDEBAR"]["navigation"]:
            for item in group["items"]:
                yield item["title"], str(item["link"])

    def test_every_menu_page_opens(self):
        self.client.force_login(self.admin)
        for title, link in self.menu_links():
            with self.subTest(страница=title):
                response = self.client.get(link, follow=True)
                self.assertEqual(response.status_code, 200)

    def test_user_add_page_opens(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/accounts/user/add/")
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_open_admin(self):
        teacher = User.objects.create_user("t@example.com", "TaynaParola123", role=User.Role.TEACHER)
        self.client.force_login(teacher)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)  # пренасочва към входа на admin
