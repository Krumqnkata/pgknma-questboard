import logging

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Guild, SchoolClass, User


class GuildSeedTests(TestCase):
    def test_four_guilds_exist(self):
        names = set(Guild.objects.values_list("name", flat=True))
        self.assertEqual(names, {"Builders", "Guardians", "Explorers", "Citizens"})


class UserRoleTests(TestCase):
    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="11А")
        self.guild = Guild.objects.get(name="Builders")

    def test_password_is_hashed(self):
        user = User.objects.create_user("uchenik@example.com", "TaynaParola123")
        self.assertNotEqual(user.password, "TaynaParola123")
        self.assertTrue(user.check_password("TaynaParola123"))

    def test_student_needs_nickname_class_and_guild(self):
        student = User(email="u@example.com", role=User.Role.STUDENT)
        with self.assertRaises(ValidationError):
            student.full_clean()

    def test_complete_student_is_valid(self):
        student = User(email="u@example.com", role=User.Role.STUDENT, nickname="Феникс",
                       school_class=self.school_class, guild=self.guild)
        student.set_password("TaynaParola123")
        student.full_clean()  # не трябва да хвърли грешка

    def test_teacher_does_not_need_student_fields(self):
        teacher = User(email="t@example.com", role=User.Role.TEACHER)
        teacher.set_password("TaynaParola123")
        teacher.full_clean()

    def test_only_admin_can_enter_django_admin(self):
        teacher = User.objects.create_user("t@example.com", "TaynaParola123", role=User.Role.TEACHER)
        admin = User.objects.create_superuser("a@example.com", "TaynaParola123")
        self.assertFalse(teacher.is_staff)
        self.assertTrue(admin.is_staff)
        self.assertEqual(admin.role, User.Role.ADMIN)


class LoginTests(TestCase):
    def test_login_with_email(self):
        User.objects.create_user("t@example.com", "TaynaParola123", role=User.Role.TEACHER)
        response = self.client.post(reverse("login"), {"username": "t@example.com", "password": "TaynaParola123"})
        # След входа отива на началната страница, която пък пренасочва според ролята.
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_home_without_login_is_public_landing(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Как работи")

    def test_missions_require_login(self):
        response = self.client.get(reverse("mission_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class ImportUsersTests(TestCase):
    """Внасяне на ученици и учители от CSV."""

    HEADER = "имейл,име,фамилия,роля,псевдоним,клас,гилдия\n"

    def run_import(self, rows):
        from .importer import import_users
        return import_users(self.HEADER + rows)

    def test_students_and_teachers_are_created(self):
        result = self.run_import("ivan@example.bg,Иван,Петров,ученик,Сокол,11Б,Explorers\n"
                                 "maria@example.bg,Мария,Иванова,учител,,,\n")
        self.assertTrue(result.ok, result.errors)
        student = User.objects.get(email="ivan@example.bg")
        self.assertEqual(student.nickname, "Сокол")
        self.assertEqual(str(student.school_class), "11Б")
        self.assertEqual(User.objects.get(email="maria@example.bg").role, User.Role.TEACHER)

    def test_temporary_password_works_and_must_be_changed(self):
        result = self.run_import("ivan@example.bg,Иван,Петров,ученик,Сокол,11Б,Explorers\n")
        user = User.objects.get(email="ivan@example.bg")
        self.assertTrue(user.check_password(result.created[0].password))
        self.assertTrue(user.must_change_password)
        self.assertNotEqual(user.password, result.created[0].password)  # в базата е само хешът

    def test_one_bad_row_imports_nothing(self):
        result = self.run_import("ivan@example.bg,Иван,Петров,ученик,Сокол,11Б,Explorers\n"
                                 "bad-email,Мария,Иванова,ученик,Лъв,11Б,Builders\n")
        self.assertFalse(result.ok)
        self.assertIn("Ред 3", result.errors[0])
        self.assertFalse(User.objects.filter(email="ivan@example.bg").exists())

    def test_admin_role_cannot_be_imported(self):
        result = self.run_import("boss@example.bg,Шеф,Шефов,администратор,,,\n")
        self.assertFalse(result.ok)

    def test_unknown_guild_and_missing_student_fields(self):
        self.assertFalse(self.run_import("a@example.bg,А,Б,ученик,Ник,11Б,Пирати\n").ok)
        self.assertFalse(self.run_import("a@example.bg,А,Б,ученик,,,Builders\n").ok)

    def test_duplicate_nickname_is_rejected(self):
        result = self.run_import("a@example.bg,А,Б,ученик,Сокол,11Б,Builders\n"
                                 "b@example.bg,В,Г,ученик,сокол,11Б,Builders\n")
        self.assertFalse(result.ok)

    def test_existing_email_is_skipped(self):
        User.objects.create_user("ivan@example.bg", "TaynaParola123", role=User.Role.TEACHER)
        result = self.run_import("ivan@example.bg,Иван,Петров,ученик,Сокол,11Б,Explorers\n")
        self.assertTrue(result.ok)
        self.assertEqual(result.skipped, ["ivan@example.bg"])
        self.assertEqual(User.objects.get(email="ivan@example.bg").role, User.Role.TEACHER)  # не е променен

    def test_admin_import_page_shows_passwords_once(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(User.objects.create_superuser("admin@example.com", "TaynaParola123"))
        url = reverse("admin:accounts_user_import_csv")
        self.assertContains(self.client.get(url), "Внасяне на ученици и учители")

        upload = SimpleUploadedFile("hora.csv", (self.HEADER + "ivan@example.bg,Иван,Петров,ученик,Сокол,11Б,Explorers\n")
                                    .encode("utf-8"), content_type="text/csv")
        response = self.client.post(url, {"file": upload})
        self.assertContains(response, "Свали паролите")
        self.assertIn("no-cache", response["Cache-Control"])


class ForcePasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("t@example.com", "VremennaParola1", role=User.Role.TEACHER,
                                             must_change_password=True)
        self.client.force_login(self.user)

    def test_every_page_redirects_to_password_change(self):
        for url in (reverse("home"), reverse("mission_list"), "/api/me/"):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse("password_change"), fetch_redirect_response=False)

    def test_after_change_everything_works(self):
        response = self.client.post(reverse("password_change"), {
            "old_password": "VremennaParola1",
            "new_password1": "NovaSigurnaParola!42",
            "new_password2": "NovaSigurnaParola!42",
        })
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password("NovaSigurnaParola!42"))
        self.assertEqual(self.client.get(reverse("mission_list")).status_code, 200)


class LoginLockoutTests(TestCase):
    """След много грешни пароли входът спира временно (защита от отгатване)."""

    def setUp(self):
        User.objects.create_user("t@example.com", "TaynaParola123", role=User.Role.TEACHER)
        # Предупрежденията за спрян вход само пълнят изхода на тестовете
        security_log = logging.getLogger("questboard.security")
        security_log.disabled = True
        self.addCleanup(setattr, security_log, "disabled", False)

    def login(self, password, email="t@example.com", ip="10.0.0.1"):
        return self.client.post(reverse("login"), {"username": email, "password": password}, REMOTE_ADDR=ip)

    def fail(self, times, **kwargs):
        for _ in range(times):
            self.login("GreshnaParola", **kwargs)

    def test_correct_password_is_refused_while_locked(self):
        self.fail(5)
        response = self.login("TaynaParola123")
        self.assertEqual(response.status_code, 200)  # остава на входа
        self.assertContains(response, "Твърде много неуспешни опити")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_last_allowed_attempt_already_shows_the_lock(self):
        self.fail(4)
        self.assertContains(self.login("GreshnaParola"), "Опитайте отново след 15 мин.")

    def test_lock_expires(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import LoginAttempt

        self.fail(5)
        LoginAttempt.objects.update(created_at=timezone.now() - timedelta(minutes=16))
        self.assertRedirects(self.login("TaynaParola123"), reverse("home"), fetch_redirect_response=False)

    def test_attempts_during_lock_do_not_extend_it(self):
        from .models import LoginAttempt

        self.fail(12)
        self.assertEqual(LoginAttempt.objects.count(), 5)

    def test_success_clears_old_mistakes(self):
        from .models import LoginAttempt

        self.fail(4)
        self.login("TaynaParola123")
        self.assertEqual(LoginAttempt.objects.count(), 0)

    def test_email_is_case_insensitive(self):
        self.fail(5, email="T@Example.COM")
        self.assertContains(self.login("TaynaParola123"), "Твърде много неуспешни опити")

    def test_one_address_trying_many_emails_is_stopped(self):
        for number in range(20):
            self.login("GreshnaParola", email=f"user{number}@example.com")
        self.assertContains(self.login("TaynaParola123"), "Твърде много неуспешни опити")
        # от друг адрес същият имейл влиза нормално
        response = self.login("TaynaParola123", ip="10.0.0.2")
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_limits_come_from_game_settings(self):
        from economy.models import GameSettings

        game = GameSettings.load()
        game.login_max_attempts, game.login_lockout_minutes = 2, 3
        game.save()
        self.fail(2)
        self.assertContains(self.login("TaynaParola123"), "след 3 мин.")

    def test_admin_login_is_protected_too(self):
        User.objects.create_superuser("a@example.com", "TaynaParola123")
        url = reverse("admin:login")
        for _ in range(5):
            self.client.post(url, {"username": "a@example.com", "password": "Greshna"}, REMOTE_ADDR="10.0.0.9")
        response = self.client.post(url, {"username": "a@example.com", "password": "TaynaParola123"},
                                    REMOTE_ADDR="10.0.0.9")
        self.assertContains(response, "Твърде много неуспешни опити")

    def test_forwarded_address_is_read_only_behind_proxy(self):
        from django.test import RequestFactory, override_settings

        from .lockout import client_ip

        request = RequestFactory().get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4")
        self.assertEqual(client_ip(request), "127.0.0.1")  # без прокси заглавката може да е подправена
        with override_settings(BEHIND_PROXY=True):
            self.assertEqual(client_ip(request), "1.2.3.4")  # адресът, добавен от нашия прокси
