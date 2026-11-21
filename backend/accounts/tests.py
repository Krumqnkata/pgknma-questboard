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

    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
