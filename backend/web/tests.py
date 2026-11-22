"""Тестове на страниците: кой какво може да отвори и направи."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild
from accounts.testing import make_mission, make_student, make_teacher
from economy.models import CoinTransaction, Privilege, Purchase
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

    def test_student_home_shows_stats(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Здравей, Феникс")
        self.assertContains(response, "0<small> от 5</small>")
        self.assertContains(response, "player.ts")  # панелът с данните на ученика

    def test_teacher_home_is_review_list(self):
        self.client.force_login(self.teacher)
        self.assertRedirects(self.client.get(reverse("home")), reverse("review_list"))


class GamePageTests(TestCase):
    """Проверка на заявки, магазин, привилегии и класация през страниците."""

    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher, title="Репортаж", xp=60)
        self.claim = Claim.objects.create(mission=self.mission, student=self.student, evidence="връзка")

    def review(self, decision, user=None, comment=""):
        self.client.force_login(user or self.teacher)
        return self.client.post(reverse("review_claim", args=[self.claim.pk]),
                                {"decision": decision, "comment": comment}, follow=True)

    def test_teacher_sees_pending_claim(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("review_list"))
        self.assertContains(response, "Репортаж")
        self.assertContains(response, 'aria-label="1 чакат"')

    def test_teacher_approves_claim(self):
        response = self.review("approve")
        self.assertContains(response, "Феникс получава 60 XP и 1 монета.")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.APPROVED)

    def test_double_click_on_approve_shows_error(self):
        self.review("approve")
        response = self.review("approve")
        self.assertContains(response, "вече е проверена")

    def test_teacher_rejects_with_comment(self):
        self.review("reject", comment="Липсва снимка")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.REJECTED)
        self.assertEqual(self.claim.review_comment, "Липсва снимка")

    def test_student_cannot_review(self):
        response = self.review("approve", user=self.student)
        self.assertEqual(response.status_code, 403)

    def test_review_does_not_redirect_to_other_sites(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("review_claim", args=[self.claim.pk]),
                                    {"decision": "approve", "next": "https://evil.example.com/"})
        self.assertRedirects(response, reverse("review_list"), fetch_redirect_response=False)

    def test_student_buys_in_shop(self):
        self.review("approve")  # 60 XP → 1 монета
        CoinTransaction.objects.create(student=self.student, amount=1, kind="correction", reason="тест")
        self.client.force_login(self.student)
        hint = Privilege.objects.get(code="hint_token")
        response = self.client.post(reverse("shop_buy", args=[hint.pk]), follow=True)
        self.assertContains(response, "Купено: Hint Token")

    def test_shop_refuses_without_coins(self):
        self.client.force_login(self.student)
        hint = Privilege.objects.get(code="hint_token")
        response = self.client.post(reverse("shop_buy", args=[hint.pk]), follow=True)
        self.assertContains(response, "Нямаш достатъчно монети")

    def test_teacher_marks_purchase_used(self):
        CoinTransaction.objects.create(student=self.student, amount=5, kind="correction", reason="тест")
        purchase = Purchase.objects.create(student=self.student, privilege=Privilege.objects.get(code="deadline_pass"),
                                           price_paid=3)
        self.client.force_login(self.teacher)
        self.client.post(reverse("purchase_use", args=[purchase.pk]))
        purchase.refresh_from_db()
        self.assertTrue(purchase.is_used)

    def test_leaderboard_shows_nicknames_not_real_names(self):
        self.student.first_name, self.student.last_name = "Калина", "Петкова"
        self.student.save()
        self.review("approve")
        self.client.force_login(make_student("drug@example.com", nickname="Сокол"))
        response = self.client.get(reverse("leaderboard"))
        self.assertContains(response, "Феникс")
        self.assertNotContains(response, "Калина")
        self.assertNotContains(response, "Петкова")


class ErrorPageTests(TestCase):
    def test_404_page_is_in_bulgarian(self):
        response = self.client.get("/няма-такава-страница/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Страницата не е намерена", status_code=404)


class SchoolBrandingTests(TestCase):
    """Името и логото на училището – качват се от администрацията."""

    def setUp(self):
        import tempfile

        from django.test import override_settings

        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.media.cleanup()

    @staticmethod
    def png(size=(8, 8)):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", size, "red").save(buffer, "PNG")
        return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")

    @staticmethod
    def form(files, name="ПГ по компютърни науки"):
        from django.forms import modelform_factory

        from economy.models import GameSettings

        form_class = modelform_factory(GameSettings, fields=["school_name", "school_logo"])
        return form_class(data={"school_name": name}, files=files, instance=GameSettings.load())

    def test_without_logo_nothing_is_shown(self):
        self.assertEqual(self.client.get(reverse("school_logo")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("home")), "brand-logo")

    def test_uploaded_logo_is_shown_and_served(self):
        form = self.form({"school_logo": self.png()})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        page = self.client.get(reverse("home"))
        self.assertContains(page, "brand-logo")
        self.assertContains(page, "ПГ по компютърни науки")

        logo = self.client.get(reverse("school_logo"))
        self.assertEqual(logo.status_code, 200)
        self.assertEqual(logo["Content-Type"], "image/png")
        logo.close()  # FileResponse държи файла отворен, докато отговорът не се затвори

    def test_svg_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        svg = SimpleUploadedFile("logo.svg", b"<svg><script>alert(1)</script></svg>", content_type="image/svg+xml")
        self.assertFalse(self.form({"school_logo": svg}).is_valid())

    def test_file_that_is_not_an_image_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("logo.png", b"not really a picture", content_type="image/png")
        self.assertFalse(self.form({"school_logo": fake}).is_valid())

    def test_too_big_logo_is_rejected(self):
        from unittest.mock import patch

        with patch("economy.models.LOGO_MAX_BYTES", 10):
            self.assertFalse(self.form({"school_logo": self.png()}).is_valid())
