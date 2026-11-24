"""Домашните: само за класа, без гилдия, с XP за предадена работа."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SchoolClass
from accounts.testing import make_mission, make_student, make_teacher
from badges.services import progress_for
from economy.services import approve_claim, xp_total
from missions.models import Mission
from missions.services import GameRuleError, missions_for_student, submit_claim


class HomeworkTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()                       # 11А
        self.other = make_student("x@example.com", "Комета")
        self.other.school_class = SchoolClass.objects.create(name="9В")
        self.other.save()
        self.homework = self.make()

    def make(self, **fields):
        homework = make_mission(self.teacher, title="Задача 5", guild=None, xp=10, kind=Mission.Kind.HOMEWORK,
                                subject="Математика", **fields)
        homework.school_classes.add(self.student.school_class)
        return homework

    def test_only_the_class_sees_it(self):
        self.assertIn(self.homework, missions_for_student(self.student))
        self.assertNotIn(self.homework, missions_for_student(self.other))
        self.assertNotIn(self.homework, missions_for_student())  # публичната страница
        url = reverse("mission_detail", args=[self.homework.pk])
        for user, status in ((self.student, 200), (self.other, 404), (self.teacher, 200)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, status)

    def test_only_the_class_can_submit(self):
        with self.assertRaises(GameRuleError):
            submit_claim(self.other, self.homework, "Готово")
        self.client.force_login(self.other)
        response = self.client.post(f"/api/missions/{self.homework.pk}/claim/", {"evidence": "Готово"})
        self.assertEqual(response.status_code, 400)

    def test_teammate_from_another_class_is_refused(self):
        self.homework.is_group = True
        self.homework.save()
        with self.assertRaises(GameRuleError):
            submit_claim(self.student, self.homework, "Готово", teammates=["Комета"])

    def test_accepted_homework_gives_xp(self):
        approve_claim(submit_claim(self.student, self.homework, "Готово"), self.teacher)
        self.assertEqual(xp_total(self.student), 10)
        self.assertIn("Домашна", self.student.xp_transactions.get().reason)
        progress = progress_for(self.student)
        self.assertEqual((progress.missions, progress.by_guild), (1, {}))  # не се брои за гилдия

    def test_rules(self):
        self.homework.xp = 100  # над лимита за домашна
        with self.assertRaises(ValidationError):
            self.homework.clean()
        with self.assertRaises(ValidationError):
            Mission(title="x", xp=10, deadline=timezone.now() + timedelta(days=1)).clean()  # мисия без гилдия

    def test_teacher_creates_homework(self):
        self.client.force_login(self.teacher)
        deadline = timezone.localtime(timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        data = {"title": "Есе", "subject": "БЕЛ", "school_classes": [self.student.school_class_id], "description": "Напиши есе.",
                "criteria": "Поне една страница.", "xp": 15, "deadline": deadline}
        response = self.client.post(reverse("homework_create"), data, follow=True)
        homework = Mission.objects.get(title="Есе")
        self.assertTrue(homework.is_homework)
        self.assertContains(response, "БЕЛ")
        self.client.post(reverse("mission_edit", args=[homework.pk]), {**data, "xp": 12, "is_active": "on"})
        homework.refresh_from_db()
        self.assertEqual((homework.xp, homework.kind), (12, "homework"))

    def test_pages(self):
        self.client.force_login(self.student)
        for name in ("home", "mission_list"):
            page = self.client.get(reverse(name))
            self.assertContains(page, "Домашна")
            self.assertContains(page, "Математика")
        self.assertContains(self.client.get(reverse("mission_list"), {"kind": "homework"}), "Задача 5")
        self.assertEqual(self.client.get("/api/missions/").json()[0]["guild_name"], None)
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("mission_list")), "Математика")


class LeaderboardTopTests(TestCase):
    def test_top_10_and_100(self):
        from economy.models import XPTransaction

        students = [make_student(f"s{i}@example.com", f"Ученик{i:02d}") for i in range(12)]
        for i, student in enumerate(students):
            XPTransaction.objects.create(student=student, amount=(12 - i) * 10, reason="тест")
        self.client.force_login(students[11])
        page = self.client.get(reverse("leaderboard"))
        self.assertEqual(len(page.context["student_rows"]), 10)
        self.assertEqual(page.context["my_row"].rank, 12)  # собственият ред се вижда винаги
        self.assertEqual([row.name for row in page.context["podium"]], ["Ученик00", "Ученик01", "Ученик02"])
        self.assertEqual(len(self.client.get(reverse("leaderboard"), {"top": "100"}).context["student_rows"]), 12)
