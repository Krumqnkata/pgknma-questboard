"""Тестовете на гилдиите: код от учителя, време на сървъра, резултат, анулиране."""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.guilds import leave_guild, make_main
from accounts.models import Guild
from accounts.testing import make_student, make_teacher
from economy.leaderboard import guild_ranking, student_ranking
from economy.services import award_xp, xp_total
from missions.errors import GameRuleError

from .models import Attempt, GuildTest, Question, normalize
from .services import (
    answer_question, close_session, current_question, note_left_page, open_session, save_drafts, start_attempt,
    tests_for, void_attempt, why_not,
)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = make_teacher()
        self.student = make_student()  # Техничари
        self.artists = Guild.objects.get(code="artists")
        self.entry = self.make_test(self.artists)

    def make_test(self, guild, kind=GuildTest.Kind.ENTRY, questions=5, **fields):
        test = GuildTest.objects.create(guild=guild, kind=kind, title="Тест", created_by=self.teacher, seconds=10,
                                        questions_count=questions, **fields)
        for i in range(questions):
            Question.objects.create(test=test, text=f"Въпрос {i}?", answers=f"*вярно {i}\nгрешно\nдруго\nнищо")
        return test

    def start(self, test=None, student=None, minutes=15):
        session = open_session(self.teacher, test or self.entry, minutes)
        return start_attempt(student or self.student, session.code)

    def right(self, attempt, question):
        return next(str(n) for n, text in question.shuffled(attempt.secret) if text.startswith("вярно"))

    def wrong(self, attempt, question):
        return next(str(n) for n, text in question.shuffled(attempt.secret) if not text.startswith("вярно"))

    def solve(self, attempt, good):
        """Решава всички въпроси, от които good са верни."""
        for i in range(attempt.total):
            question, _ = current_question(attempt)
            answer_question(attempt, question.pk, (self.right if i < good else self.wrong)(attempt, question))
        attempt.refresh_from_db()
        self.student.refresh_from_db()
        return attempt


class EntryTests(Base):
    def test_pass_at_80_percent_joins_the_guild(self):
        attempt = self.solve(self.start(), 4)
        self.assertEqual((attempt.status, attempt.percent), (Attempt.Status.PASSED, 80))
        self.assertEqual(self.student.guild.code, "techies")           # първата остава основна
        self.assertEqual(self.student.second_guild, self.artists)

    def test_third_guild_is_refused(self):
        self.solve(self.start(), 5)
        third = self.make_test(Guild.objects.get(code="athletes"))
        self.assertIn("2 гилдии", why_not(self.student, third))
        leave_guild(self.student, self.artists)
        self.student.refresh_from_db()
        self.assertEqual(why_not(self.student, third), "")

    def test_main_guild_is_swapped_once_in_30_days(self):
        self.solve(self.start(), 5)
        self.client.force_login(self.student)
        self.client.post(reverse("guild_main", args=[self.artists.pk]))
        self.student.refresh_from_db()
        self.assertEqual([guild.code for guild in self.student.guilds], ["artists", "techies"])
        self.assertContains(self.client.get(reverse("home")), 'class="themed accent-artists"')
        with self.assertRaises(GameRuleError):
            make_main(self.student, self.student.second_guild)
        self.client.post(reverse("guild_leave", args=[self.artists.pk]))
        self.student.refresh_from_db()
        self.assertEqual([guild.code for guild in self.student.guilds], ["techies"])  # втората става основна

    def test_xp_counts_for_the_main_guild_only(self):
        self.solve(self.start(), 5)
        award_xp(self.student, 50, "тест")
        xp = {row.code: row.xp for row in guild_ranking()}
        self.assertEqual((xp["techies"], xp["artists"]), (50, 0))
        self.assertEqual(len(student_ranking(guild_id=self.artists.pk)), 1)  # но се вижда и в двете

    def test_members_of_the_second_guild_take_the_monthly_test(self):
        self.solve(self.start(), 5)
        monthly = self.make_test(self.artists, GuildTest.Kind.MONTHLY, xp=40)
        self.assertEqual(why_not(self.student, monthly), "")

    def test_below_80_stays_and_waits_seven_days(self):
        attempt = self.solve(self.start(), 3)
        self.assertEqual(attempt.status, Attempt.Status.FAILED)
        self.assertEqual(self.student.guild.code, "techies")
        self.assertIn("Нов опит", why_not(self.student, self.entry))
        with self.assertRaises(GameRuleError):
            self.start()
        self.assertEqual(why_not(self.student, self.entry, timezone.now() + timedelta(days=8)), "")

    def test_member_cannot_take_the_entry_test(self):
        self.assertIn("Вече си", why_not(self.student, self.make_test(self.student.guild)))

    def test_student_without_guild_can_join(self):
        self.student.guild = None
        self.student.full_clean()
        self.student.save()
        self.solve(self.start(), 5)
        self.assertEqual(self.student.guild, self.artists)


class MonthlyTests(Base):
    def setUp(self):
        super().setUp()
        self.monthly = self.make_test(self.student.guild, GuildTest.Kind.MONTHLY, xp=40)

    def test_pass_gives_xp_once_a_month(self):
        self.solve(self.start(self.monthly), 5)
        self.assertEqual(xp_total(self.student), 40)
        self.assertIn("този месец", why_not(self.student, self.monthly))
        self.assertEqual(why_not(self.student, self.monthly, timezone.now() + timedelta(days=32)), "")

    def test_fail_gives_nothing_and_strangers_cannot_start(self):
        self.solve(self.start(self.monthly), 2)
        self.assertEqual(xp_total(self.student), 0)
        stranger = make_student("x@example.com", "Комета", "Артисти")
        with self.assertRaises(GameRuleError):
            self.start(self.monthly, stranger)

    def test_xp_is_limited(self):
        with self.assertRaises(ValidationError):
            GuildTest(guild=self.artists, kind="monthly", title="x", xp=5000, created_by=self.teacher).full_clean()


class SessionTests(Base):
    def test_no_code_no_test(self):
        for code in ("", "000000", "абв"):
            with self.assertRaises(GameRuleError):
                start_attempt(self.student, code)

    def test_too_many_wrong_codes(self):
        session = open_session(self.teacher, self.entry, 15)
        for _ in range(10):
            with self.assertRaises(GameRuleError):
                start_attempt(self.student, "123")
        with self.assertRaisesMessage(GameRuleError, "Твърде много"):
            start_attempt(self.student, session.code)

    def test_closed_session_accepts_nobody_but_started_can_finish(self):
        session = open_session(self.teacher, self.entry, 15)
        attempt = start_attempt(self.student, session.code)
        close_session(self.teacher, session)
        with self.assertRaises(GameRuleError):
            start_attempt(make_student("x@example.com", "Комета"), session.code)
        self.assertEqual(self.solve(attempt, 5).status, Attempt.Status.PASSED)

    def test_rules_for_opening(self):
        with self.assertRaises(GameRuleError):
            open_session(self.student, self.entry, 15)
        with self.assertRaises(GameRuleError):
            open_session(self.teacher, self.make_test(self.artists, questions=2), 15)
        self.entry.questions.update(is_approved=False)  # черновите не се броят
        with self.assertRaises(GameRuleError):
            open_session(self.teacher, self.entry, 15)

    def test_double_click_gives_one_attempt(self):
        session = open_session(self.teacher, self.entry, 15)
        self.assertEqual(start_attempt(self.student, session.code), start_attempt(self.student, session.code))


class TimeTests(Base):
    def test_late_answer_is_wrong(self):
        attempt = self.start()
        question, left = current_question(attempt)
        self.assertLessEqual(left, 10)
        answer_question(attempt, question.pk, self.right(attempt, question), timezone.now() + timedelta(seconds=13))
        attempt.refresh_from_db()
        self.assertEqual((attempt.position, attempt.correct), (1, 0))

    def test_reload_does_not_restart_the_clock(self):
        attempt = self.start()
        now = timezone.now()
        first, _ = current_question(attempt, now)
        again, left = current_question(attempt, now + timedelta(seconds=6))
        self.assertEqual(first, again)
        self.assertAlmostEqual(left, 4, delta=0.1)

    def test_skipped_question_is_lost(self):
        attempt = self.start()
        now = timezone.now()
        first, _ = current_question(attempt, now)
        second, _ = current_question(attempt, now + timedelta(seconds=20))
        self.assertNotEqual(first, second)
        answer_question(attempt, first.pk, self.right(attempt, first))  # върната страница
        attempt.refresh_from_db()
        self.assertEqual((attempt.position, attempt.correct), (1, 0))

    def test_abandoned_attempt_ends(self):
        attempt = self.start()
        current_question(attempt)
        self.assertIsNone(current_question(attempt, attempt.deadline + timedelta(seconds=1)))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.FAILED)

    def test_question_that_was_not_shown_cannot_be_answered(self):
        attempt = self.start()
        question = Question.objects.get(pk=attempt.question_ids[0])
        answer_question(attempt, question.pk, self.right(attempt, question))
        attempt.refresh_from_db()
        self.assertEqual(attempt.position, 0)


class QuestionTests(Base):
    def question(self, kind, answers):
        question = Question(test=self.entry, kind=kind, text="Задача?", answers=answers)
        question.full_clean()
        question.save()
        return question

    def test_order(self):
        question = self.question("order", "едно\nдве\nтри\nчетири")
        place = {text: n for n, text in question.shuffled("тайна")}
        good = ",".join(str(place[text]) for text in ("едно", "две", "три", "четири"))
        self.assertTrue(question.is_correct(good, "тайна"))
        self.assertFalse(question.is_correct(",".join(reversed(good.split(","))), "тайна"))
        for bad in ("", "x", "0,1", "9,9,9,9"):
            self.assertFalse(question.is_correct(bad, "тайна"))

    def test_text(self):
        question = self.question("text", "print(1)\nprint( \"1\" )")
        for value in ("print(1)", " Print( 1 ) ;", 'print("1")'):
            self.assertTrue(question.is_correct(value, "x"), value)
        for value in ("", "print(2)"):
            self.assertFalse(question.is_correct(value, "x"))
        self.assertEqual(normalize("  А Б. "), "аб")

    def test_bad_questions_are_refused(self):
        for kind, answers in (("choice", "а\nб"), ("choice", "*а\n*б"), ("choice", "*а"), ("choice", "*а\nа"),
                              ("order", "а\nб"), ("order", "а\nа\nб"), ("text", " ")):
            with self.assertRaises(ValidationError):
                self.question(kind, answers)

    def test_drafts_wait_for_approval(self):
        saved = save_drafts(self.entry, [
            {"text": "Колко е 2+2?", "options": ["3", "4", "5", "6"], "correct": 1},
            {"text": "Лош?", "options": ["а", "а", "б", "в"], "correct": 0},
        ])
        self.assertEqual(saved, 1)
        draft = self.entry.questions.get(is_approved=False)
        self.assertEqual(draft.lines[1], "*4")


class VoidTests(Base):
    def test_entry_goes_back(self):
        attempt = self.solve(self.start(), 5)
        with self.assertRaises(GameRuleError):
            void_attempt(make_teacher("other@example.com"), attempt, "преписване")
        void_attempt(self.teacher, attempt, "преписване")
        self.student.refresh_from_db()
        self.assertEqual((self.student.guild.code, self.student.second_guild), ("techies", None))
        self.assertEqual(why_not(self.student, self.entry), "")  # анулираният не се брои

    def test_xp_goes_back(self):
        attempt = self.solve(self.start(self.make_test(self.student.guild, GuildTest.Kind.MONTHLY, xp=40)), 5)
        void_attempt(self.teacher, attempt, "преписване")
        self.assertEqual(xp_total(self.student), 0)


class PageTests(Base):
    def test_whole_test_through_the_pages(self):
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("guild_list")), "Код от учителя")
        session = open_session(self.teacher, self.entry, 15)
        response = self.client.post(reverse("test_start"), {"code": f"{session.code[:3]} {session.code[3:]}"}, follow=True)
        attempt = Attempt.objects.get()
        url = reverse("test_attempt", args=[attempt.pk])
        for _ in range(5):
            question = response.context["question"]
            self.assertNotContains(response, "*вярно")  # знакът за верен отговор не стига до браузъра
            self.assertIn("no-store", response["Cache-Control"])
            response = self.client.post(url, {"question": question.pk, "answer": self.right(attempt, question)}, follow=True)
        self.assertContains(response, "Вече си в гилдия")
        self.assertContains(self.client.get(reverse("guild_list")), "Моите опити")

    def test_student_sees_only_own_attempt_and_no_teacher_pages(self):
        attempt = self.start()
        other = make_student("x@example.com", "Комета")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("test_attempt", args=[attempt.pk])).status_code, 404)
        for name, args in (("test_list", []), ("test_edit", [self.entry.pk]), ("test_session", [attempt.session_id])):
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)

    def test_teacher_pages(self):
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("test_list")), "Тест")
        self.client.post(reverse("test_edit", args=[self.entry.pk]), {
            "action": "question", "kind": "choice", "text": "Нов въпрос?", "answers": "*да\nне"})
        self.assertTrue(self.entry.questions.filter(text="Нов въпрос?").exists())
        self.client.post(reverse("session_open", args=[self.entry.pk]), {"minutes": 10})
        session = self.entry.sessions.get()
        attempt = start_attempt(self.student, session.code)
        page = self.client.get(reverse("test_session", args=[session.pk]))
        self.assertContains(page, session.code)
        self.assertContains(page, self.student.nickname)
        self.client.post(reverse("test_session", args=[session.pk]), {"action": "void", "attempt": attempt.pk, "why": "преписва"})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.VOID)
        other = make_teacher("other@example.com")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("test_edit", args=[self.entry.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("test_session", args=[session.pk])).status_code, 404)

    def test_create_and_drafts(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("test_create"), {"guild": self.artists.pk, "kind": "entry", "title": "Нов", "questions_count": 5,
                                                  "seconds": 12, "pass_percent": 80, "xp": 0, "retry_days": 7, "is_active": "on"})
        test = GuildTest.objects.get(title="Нов")
        reply = {"questions": [{"text": "Колко е 2+2?", "options": ["3", "4", "5", "6"], "correct": 1}]}
        with patch("assistant_bridge.client.call", return_value=reply):
            page = self.client.post(reverse("test_edit", args=[test.pk]), {"action": "draft", "topic": "математика", "count": 1},
                                    follow=True)
        self.assertContains(page, "чернова")
        question = test.questions.get()
        self.client.post(reverse("test_edit", args=[test.pk]), {"action": "approve", "question": question.pk})
        question.refresh_from_db()
        self.assertTrue(question.is_approved)

    def test_leaving_the_page_is_counted(self):
        attempt = self.start()
        self.client.force_login(self.student)
        self.client.post(reverse("test_left", args=[attempt.pk]))
        note_left_page(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.left_page, 2)

    def test_guild_list_shows_only_ready_tests(self):
        self.make_test(self.artists, questions=1)
        self.assertEqual([test for test, _ in tests_for(self.student)], [self.entry])

    def test_kit_switch_and_privacy(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, 'data-kit-set="gamer"')
        self.assertContains(page, "css/gamer.css")
        self.assertContains(self.client.get(reverse("privacy")), "Тестове: отговорите")
