"""Шегата за ботовете, които търсят WordPress (web/views/not_wordpress.py)."""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import BotKnock


class NotWordPressTests(TestCase):
    def test_wordpress_paths_answer_418(self):
        for path in ("/wp-admin/", "/wp-admin", "/wp-admin/install.php", "/wp-login.php", "/xmlrpc.php",
                     "/wp-content/plugins/x.php", "/wp-includes/x.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 418)
                self.assertContains(response, "Това не е WordPress.", status_code=418)

    def test_post_without_csrf_still_gets_the_joke(self):
        # Ботовете пращат пароли с POST – страницата не ги чете и не дава грешка 403.
        response = self.client.post("/wp-login.php", {"log": "admin", "pwd": "123456"})
        self.assertEqual(response.status_code, 418)
        self.assertNotContains(response, "123456", status_code=418)

    def test_page_has_no_form(self):
        response = self.client.get("/wp-admin/")
        self.assertNotContains(response, "<form", status_code=418)
        self.assertNotContains(response, 'type="password"', status_code=418)

    def test_hits_are_counted_per_day_without_ip(self):
        self.client.get("/wp-admin/")
        self.client.get("/wp-login.php")
        knock = BotKnock.objects.get(day=timezone.localdate())
        self.assertEqual(knock.hits, 2)
        self.assertEqual({field.name for field in BotKnock._meta.fields}, {"id", "day", "hits"})

    def test_dashboard_shows_the_count(self):
        self.client.get("/wp-admin/")
        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Ботове, търсили WordPress")
