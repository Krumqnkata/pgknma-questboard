"""Следващата стъпка, първите стъпки, късата форма, бързата проверка и менюто на учителя."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.testing import make_mission, make_student, make_teacher
from economy.models import CoinTransaction, Privilege, Purchase, XPTransaction
from economy.services import approve_claim, reject_claim, student_stats, xp_total
from missions.models import Claim, Mission
from missions.services import submit_claim
from notifications.models import Notification
from web.cycle import days_left, first_steps, student_cycle, teacher_cycle
from web.forms import HomeworkForm, MissionForm


class StudentCycleTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()

    def now(self, suggested=()):
        cycle = student_cycle(self.student, student_stats(self.student), suggested)
        return cycle.headline, [step.is_now for step in cycle.steps].index(True)

    def test_nothing_to_do(self):
        self.assertIn("Няма нови мисии", self.now()[0])

    def test_rejected_claim_comes_first(self):
        mission = make_mission(self.teacher, title="Базар")
        reject_claim(submit_claim(self.student, mission, "Готово"), self.teacher, "Липсва снимка")
        headline, step = self.now([make_mission(self.teacher, title="Друга")])
        self.assertIn("„Базар“ е върната", headline)
        self.assertEqual(step, 1)

    def test_homework_due_tomorrow(self):
        homework = make_mission(self.teacher, guild=None, kind=Mission.Kind.HOMEWORK, subject="Математика", xp=10,
                                deadline=timezone.now() + timedelta(days=1))
        homework.school_classes.add(self.student.school_class)
        self.assertIn("Домашната по Математика е до утре", self.now()[0])

    def test_mission_that_gives_the_next_level(self):
        XPTransaction.objects.create(student=self.student, amount=80, reason="тест")
        mission = make_mission(self.teacher, title="Плакат", xp=40)
        self.assertIn("Още 20 XP до ниво 2. „Плакат“ дава 40", self.now([mission])[0])

    def test_coins_for_a_reward(self):
        Privilege.objects.exclude(code="hint_token").update(is_active=False)
        CoinTransaction.objects.create(student=self.student, amount=2, kind="earned", reason="тест")
        headline, step = self.now([make_mission(self.teacher, title="Малка", xp=10)])
        self.assertIn("Стигат за „Подсказка“", headline)
        self.assertEqual(step, 3)

    def test_waiting_for_the_teacher(self):
        submit_claim(self.student, make_mission(self.teacher), "Готово")
        self.assertEqual(self.now(), ("Всичко е подадено. Сега учителят проверява.", 2))

    def test_days_left(self):
        self.assertEqual([days_left(timezone.now() + timedelta(days=n)) for n in (0, 1, 3)], ["е до днес", "е до утре", "има срок още 3 дни"])

    def test_first_steps_disappear(self):
        def titles():
            return [step.done for step in first_steps(self.student, student_stats(self.student))]

        self.assertEqual(titles(), [True, False, False, False])
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("home")), "Първи стъпки")
        claim = submit_claim(self.student, make_mission(self.teacher, xp=60), "Готово")
        approve_claim(claim, self.teacher)
        self.assertEqual(titles(), [])
        self.assertNotContains(self.client.get(reverse("home")), "Първи стъпки")


class TeacherCycleTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()

    def now(self):
        pending = Claim.objects.filter(status=Claim.Status.PENDING).count()
        cycle = teacher_cycle(self.teacher, pending)
        return [step.is_now for step in cycle.steps].index(True)

    def test_whole_circle(self):
        self.assertEqual(self.now(), 0)  # задай
        mission = make_mission(self.teacher, xp=60)
        claim = submit_claim(self.student, mission, "Готово")
        self.assertEqual(self.now(), 1)  # провери
        approve_claim(claim, self.teacher)
        self.assertEqual(self.now(), 3)  # виж резултата
        self.assertIn("1 потвърдени, 1 ученици, 60 XP", teacher_cycle(self.teacher, 0).steps[3].text)
        Purchase.objects.create(student=self.student, privilege=Privilege.objects.create(code="topic", name="Избор на тема", price=3), price_paid=3)
        self.assertEqual(self.now(), 2)  # награди

    def test_bulk_approve(self):
        claims = [submit_claim(self.student, make_mission(self.teacher, title=f"М{n}", xp=10), "Готово") for n in range(3)]
        foreign = submit_claim(self.student, make_mission(make_teacher("drug@example.com"), title="Чужда"), "Готово")
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("review_list"))
        self.assertContains(page, "Потвърди избраните")
        self.assertContains(page, "Липсва снимка.")
        response = self.client.post(reverse("review_bulk"), {"claim": [claims[0].pk, claims[1].pk, foreign.pk, "x"]}, follow=True)
        self.assertContains(response, "Потвърдени: 2. Учениците получават общо 20 XP.")
        self.assertEqual(xp_total(self.student), 20)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, Claim.Status.PENDING)  # чуждата не минава
        self.client.post(reverse("review_bulk"), {"claim": [claims[0].pk]})  # второ натискане не дава XP пак
        self.assertEqual(xp_total(self.student), 20)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse("review_bulk"), {"claim": [claims[2].pk]}).status_code, 403)

    def test_menu_has_five_items(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("review_list")).content.decode()
        nav = page[page.index('<nav class="nav"'):page.index("</nav>")]
        for text in ("Днес", "Мисии", "Гилдии", "Награди", "Още"):
            self.assertIn(text, nav)
        for name, other in (("guild_list", "test_list"), ("test_list", "guild_list"), ("purchase_list", "rewards"),
                            ("rewards", "purchase_list")):
            self.assertContains(self.client.get(reverse(name)), reverse(other))


class ShortFormTests(TestCase):
    def test_only_six_fields_are_visible(self):
        form = MissionForm(instance=Mission(created_by=make_teacher()))
        self.assertEqual([field.name for field in form.main_fields], ["title", "description", "criteria", "guild", "xp", "deadline"])
        self.assertFalse(form.more_open)
        self.assertEqual(len(form.main_fields) + len(form.more_fields), len(form.fields))  # нищо не се губи
        self.assertEqual(len(HomeworkForm(instance=Mission(created_by=form.instance.created_by, kind="homework")).main_fields), 7)

    def test_opens_when_something_is_set_or_wrong(self):
        teacher = make_teacher()
        mission = make_mission(teacher, is_group=True)
        self.assertTrue(MissionForm(instance=mission).more_open)
        self.client.force_login(teacher)
        page = self.client.post(reverse("mission_create"), {"title": "x", "is_group": "on", "hints_allowed": "on", "team_min": 1})
        self.assertContains(page, '<details class="more-fields" open>')


class RewardNoticeTests(TestCase):
    def test_item_from_mission_is_not_a_bonus(self):
        teacher, student = make_teacher(), make_student()
        mission = make_mission(teacher, reward_item=Privilege.objects.get(code="title_discoverer"))
        approve_claim(submit_claim(student, mission, "Готово"), teacher)
        notice = student.notifications.get(text__startswith="Спечели")
        self.assertEqual(notice.kind, Notification.Kind.REWARD)
        self.client.force_login(student)
        self.assertNotContains(self.client.get(reverse("home")), "Бонус от учител")

    def test_names_are_in_bulgarian(self):
        self.assertEqual(Privilege.objects.get(code="deadline_pass").name, "Удължен срок")
        self.assertEqual(Privilege.objects.get(code="hint_token").name, "Подсказка")
        self.assertNotContains(self.client.get(reverse("terms")), "Hint Token")


class OrderTests(TestCase):
    """annotate(Count(...)) изхвърля подредбата от модела, затова се пише изрично."""

    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()

    def deadlines(self, *days):
        return [make_mission(self.teacher, title=f"след {n}", deadline=timezone.now() + timedelta(days=n)) for n in days]

    def test_student_list_by_deadline(self):
        self.deadlines(9, 2, 5)
        self.client.force_login(self.student)
        rows = self.client.get(reverse("mission_list")).context["rows"]
        self.assertEqual([mission.title for mission, _claim in rows], ["след 2", "след 5", "след 9"])

    def test_teacher_list_open_first(self):
        self.deadlines(9, 2, -4, -1)
        self.client.force_login(self.teacher)
        missions = self.client.get(reverse("mission_list")).context["missions"]
        self.assertEqual([mission.title for mission in missions], ["след 2", "след 9", "след -1", "след -4"])

    def test_pending_claims_first_on_the_home_page(self):
        approve_claim(submit_claim(self.student, self.deadlines(3)[0], "Готово"), self.teacher)
        waiting = submit_claim(self.student, self.deadlines(4)[0], "Готово")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("home")).context["recent_claims"][0], waiting)

    def test_weekly_board_shows_the_real_level(self):
        XPTransaction.objects.create(student=self.student, amount=600, reason="тест")
        XPTransaction.objects.update(created_at=timezone.now() - timedelta(days=30))
        XPTransaction.objects.create(student=self.student, amount=10, reason="тест")
        self.client.force_login(self.student)
        row = self.client.get(reverse("leaderboard"), {"period": "week"}).context["student_rows"][0]
        self.assertEqual((row.xp, row.level.number), (10, 4))

    def test_guilds_by_name_and_newest_session_first(self):
        from accounts.models import Guild
        from quizzes.models import GuildTest, TestSession

        self.client.force_login(self.teacher)
        names = [guild.name for guild in self.client.get(reverse("guild_list")).context["guilds"]]
        self.assertEqual(names, sorted(names))
        test = GuildTest.objects.create(guild=Guild.objects.first(), title="Тест", created_by=self.teacher)
        sessions = [TestSession.objects.create(test=test, teacher=self.teacher, code=str(n), expires_at=timezone.now())
                    for n in range(10)]
        shown = list(self.client.get(reverse("test_list")).context["sessions"])
        self.assertEqual(shown[0], sessions[-1])
        self.assertNotIn(sessions[0], shown)
