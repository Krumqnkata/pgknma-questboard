from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.testing import make_student, make_teacher
from economy.models import GameSettings

from .models import NicknameChange, User
from .nicknames import change_nickname


class NicknameChangeTests(TestCase):
    """Ученикът сменя псевдонима си сам, но по правила."""

    def setUp(self):
        self.student = make_student()  # псевдоним „Феникс“
        self.student.first_name, self.student.last_name = "Иван", "Петров"
        self.student.save()

    def change(self, value):
        return change_nickname(self.student, value)

    def refused(self, value, reason):
        with self.assertRaisesMessage(ValidationError, reason):
            self.change(value)

    def test_change_is_saved_with_history(self):
        self.assertEqual(self.change("  Сив   Вълк "), "Сив Вълк")  # излишните интервали се махат
        self.student.refresh_from_db()
        self.assertEqual(self.student.nickname, "Сив Вълк")
        entry = NicknameChange.objects.get()
        self.assertEqual((entry.old, entry.new, entry.changed_by), ("Феникс", "Сив Вълк", self.student))

    def test_length_and_characters(self):
        self.refused("Ab", "от 3 до 20 знака")
        self.refused("Много-много-дълъг-псевдоним", "от 3 до 20 знака")
        self.refused("<script>", "Позволени са само")
        self.refused("Звезда!", "Позволени са само")

    def test_taken_regardless_of_case_also_in_cyrillic(self):
        make_student("drug@example.com", nickname="Сокол")
        self.refused("СОКОЛ", "вече е зает")

    def test_same_as_current(self):
        self.refused("феникс", "вече е твоят псевдоним")

    def test_real_name_is_not_allowed(self):
        self.refused("Петров99", "истинското ти име")
        self.refused("иван_x", "истинското ти име")

    def test_banned_words_from_settings(self):
        self.refused("Учителят", "неподходяща дума")  # от началния списък
        rules = GameSettings.load()
        rules.banned_words = "глупак\nтъпак"
        rules.save()
        self.refused("Глупака", "неподходяща дума")
        self.assertEqual(self.change("Учител Нов"), "Учител Нов")  # списъкът вече е друг

    def test_once_every_30_days(self):
        self.change("Сив Вълк")
        self.refused("Бял Вълк", "веднъж на 30 дни")
        NicknameChange.objects.update(changed_at=timezone.now() - timedelta(days=31))
        self.assertEqual(self.change("Бял Вълк"), "Бял Вълк")

    def test_no_limit_when_days_is_zero(self):
        rules = GameSettings.load()
        rules.nickname_change_days = 0
        rules.save()
        self.change("Сив Вълк")
        self.assertEqual(self.change("Бял Вълк"), "Бял Вълк")

    def test_teacher_has_no_nickname(self):
        with self.assertRaises(ValidationError):
            change_nickname(make_teacher(), "Нещо")


class NicknamePageTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.client.force_login(self.student)

    def test_form_on_profile(self):
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Смяна на псевдонима")
        self.assertContains(response, "веднъж на 30 дни")

    def test_successful_change(self):
        response = self.client.post(reverse("profile"), {"nickname": "Сив Вълк"}, follow=True)
        self.assertContains(response, "Псевдонимът ти вече е „Сив Вълк“.")
        self.assertContains(response, "Следващата смяна е възможна от")  # формата изчезва до 30 дни

    def test_error_is_shown_next_to_the_field(self):
        make_student("drug@example.com", nickname="Сокол")
        response = self.client.post(reverse("profile"), {"nickname": "сокол"})
        self.assertContains(response, "вече е зает")
        self.student.refresh_from_db()
        self.assertEqual(self.student.nickname, "Феникс")

    def test_teacher_profile_has_no_form(self):
        self.client.force_login(make_teacher())
        self.assertNotContains(self.client.get(reverse("profile")), "Смяна на псевдонима")


class NicknameAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("a@example.com", "TaynaParola123")
        self.student = make_student()
        self.client.force_login(self.admin)

    def test_admin_change_is_in_history_and_does_not_start_the_wait(self):
        url = reverse("admin:accounts_user_change", args=[self.student.pk])
        form = self.client.get(url).context["adminform"].form
        data = {name: value for name, value in form.initial.items() if value is not None}
        data.update({"nickname": "Нов Ник", "school_class": self.student.school_class_id,
                     "guild": self.student.guild_id, "role": "student", "is_active": "on",
                     "nickname_changes-TOTAL_FORMS": "0", "nickname_changes-INITIAL_FORMS": "0"})
        data.pop("password", None)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.context and response.context["adminform"].form.errors)
        entry = NicknameChange.objects.get()
        self.assertEqual((entry.old, entry.new, entry.changed_by), ("Феникс", "Нов Ник", self.admin))
        # Историята се вижда на страницата на ученика в администрацията.
        page = self.client.get(url).content.decode()
        self.assertIn("история на псевдонима", page.lower())
        self.assertIn("Феникс", page)
        # Смяната от администратора не брои за ограничението от 30 дни.
        self.assertEqual(change_nickname(self.student, "Друг Ник"), "Друг Ник")
