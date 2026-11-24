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


class StaticFilesWithoutCollectstaticTests(TestCase):
    """При DEBUG=False без подготвени статични файлове страниците не трябва да дават грешка 500."""

    def test_pages_work_without_collectstatic(self):
        import tempfile

        from django.test import override_settings

        with tempfile.TemporaryDirectory() as empty_static_root, override_settings(
            STATIC_ROOT=empty_static_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "questboard.storage.ForgivingManifestStorage"},
            },
        ):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "/static/css/style.css")  # обикновеният адрес, без уникално име


class DashboardTests(TestCase):
    """Таблото на администрацията с основните числа и графики."""

    def test_axis_maximum_is_a_round_number(self):
        from .dashboard import nice_max

        self.assertEqual([nice_max(v) for v in (0, 1, 3, 7, 12, 60, 101)], [1, 1, 5, 10, 20, 100, 200])

    def test_numbers_use_bulgarian_thousands_separator(self):
        from .dashboard import number

        self.assertEqual(number(1240), "1 240")

    def test_dashboard_shows_real_data(self):
        from accounts.testing import make_mission, make_student, make_teacher
        from economy.services import approve_claim
        from missions.services import submit_claim

        teacher, student = make_teacher(), make_student()
        mission = make_mission(teacher, title="Озеленяване на двора", xp=40)
        approve_claim(submit_claim(student, mission, "Готово, ето доказателството."), teacher)
        submit_claim(student, make_mission(teacher, title="Втора мисия"), "Готово, ето доказателството.")

        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        response = self.client.get("/admin/")
        self.assertContains(response, "Потвърдени мисии по седмици")
        self.assertContains(response, "Озеленяване на двора")
        dashboard = response.context["dashboard"]
        self.assertEqual(dashboard["weekly"]["total"], 1)
        self.assertEqual(dashboard["guilds"][0]["name"], "Техничари")
        self.assertEqual(dashboard["guilds"][0]["xp"], 40)
        kpis = {kpi.label: kpi.value for kpi in dashboard["kpis"]}
        self.assertEqual(kpis["Чакащи заявки"], "1")
        self.assertEqual(kpis["XP тази седмица"], "40")

    def test_kpi_links_open(self):
        self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
        for kpi in self.client.get("/admin/").context["dashboard"]["kpis"]:
            if kpi.link:
                with self.subTest(kpi=kpi.label):
                    self.assertEqual(self.client.get(kpi.link).status_code, 200)
