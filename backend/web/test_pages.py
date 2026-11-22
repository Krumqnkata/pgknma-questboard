from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from economy.models import GameSettings

from .models import SitePage
from .templatetags.questboard import page_text


class PageTextTests(TestCase):
    """Простият формат на страниците от администрацията."""

    def test_headings_paragraphs_and_lists(self):
        html = page_text("## Заглавие\nПърви ред\nвтори ред\n\n- точка 1\n- точка 2\nСлед списъка")
        self.assertEqual(html, "<h2>Заглавие</h2>\n<p>Първи ред втори ред</p>\n"
                               "<ul><li>точка 1</li><li>точка 2</li></ul>\n<p>След списъка</p>")

    def test_html_is_escaped(self):
        html = page_text('<script>alert(1)</script>\n## <img src=x onerror="alert(1)">')
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_placeholders(self):
        html = page_text("[училище] · [имейл]", {"name": "ПГ „Пример“", "email": "info@example.bg"})
        self.assertIn("ПГ „Пример“ · info@example.bg", html)
        self.assertIn("училището", page_text("[училище]"))  # без попълнено име


class SitePageTests(TestCase):
    def test_both_pages_exist_and_are_public(self):
        for name, title in (("terms", "Условия за ползване"), ("privacy", "Политика за поверителност")):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, f"<h1>{title}</h1>", html=True)
                self.assertContains(response, "Последна промяна")

    def test_privacy_page_describes_the_assistant(self):
        self.assertContains(self.client.get(reverse("privacy")), "Към модела не се изпращат имена")

    def test_school_name_and_email_from_settings(self):
        rules = GameSettings.load()
        rules.school_name, rules.contact_email = "ПГ „Пример“", "info@example.bg"
        rules.save()
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "ПГ „Пример“")
        self.assertContains(response, "info@example.bg")

    def test_links_in_footer_and_on_login(self):
        self.assertContains(self.client.get(reverse("home")), reverse("privacy"))
        self.assertContains(self.client.get(reverse("login")), "С влизането приемате")

    def test_readable_with_temporary_password(self):
        user = User.objects.create_user("t@example.com", "VremennaParola1", role=User.Role.TEACHER,
                                        must_change_password=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("terms")).status_code, 200)


class SitePageAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        self.page = SitePage.objects.get(slug="terms")

    def test_admin_edits_the_text(self):
        url = reverse("admin:web_sitepage_change", args=[self.page.pk])
        response = self.client.post(url, {"title": "Правила", "content": "## Ново\nНов текст."})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(reverse("terms"))
        self.assertContains(page, "<h2>Ново</h2>", html=True)
        self.assertContains(page, "Нов текст.")

    def test_restore_default_text(self):
        SitePage.objects.filter(pk=self.page.pk).update(content="развалено")
        self.client.post(reverse("admin:web_sitepage_changelist"),
                         {"action": "restore_default", "_selected_action": [self.page.pk]})
        self.page.refresh_from_db()
        self.assertIn("## За платформата", self.page.content)

    def test_pages_cannot_be_added_or_deleted(self):
        self.assertEqual(self.client.get(reverse("admin:web_sitepage_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:web_sitepage_delete", args=[self.page.pk])).status_code, 403)
