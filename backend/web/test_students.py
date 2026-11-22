"""Тестове за нещата, които правят платформата по-привлекателна за учениците."""
import json
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.testing import make_mission, make_student, make_teacher
from badges.models import StudentBadge
from economy.models import CoinTransaction, GameSettings, Privilege
from economy.services import approve_claim, buy_privilege, streak_weeks, unused_purchases, wear
from missions.models import Claim
from missions.services import GameRuleError, submit_claim

from .avatars import avatar_html, cells_for
from .templatetags.questboard import difficulty, time_left


def give_coins(student, amount):
    CoinTransaction.objects.create(student=student, amount=amount, kind=CoinTransaction.Kind.EARNED, reason="тест")


def complete(teacher, student, xp=20, title="Мисия"):
    return approve_claim(submit_claim(student, make_mission(teacher, title=title, xp=xp), "Готово, ето доказателството."),
                         teacher)


class AvatarTests(TestCase):
    def setUp(self):
        self.student = make_student()

    def test_same_user_same_pattern_and_never_empty(self):
        self.assertEqual(cells_for(self.student), cells_for(self.student))
        self.assertGreaterEqual(len(cells_for(self.student)), 5)

    def test_new_pattern_with_new_seed(self):
        before = cells_for(self.student)
        patterns = set()
        for seed in range(1, 6):
            self.student.avatar_seed = seed
            patterns.add(tuple(cells_for(self.student)))
        self.assertTrue(any(pattern != tuple(before) for pattern in patterns))

    def test_html_has_guild_color_and_frame(self):
        html = avatar_html(self.student, 40, "gold")
        self.assertIn("guild-builders", html)
        self.assertIn("frame-gold", html)
        self.assertIn("--avatar-size:40px", html)

    def test_profile_button_changes_pattern(self):
        self.client.force_login(self.student)
        self.client.post(reverse("profile"), {"action": "avatar"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.avatar_seed, 1)


class GuildAccentTests(TestCase):
    def test_student_pages_use_guild_color(self):
        self.client.force_login(make_student(guild_name="Explorers"))
        self.assertContains(self.client.get(reverse("home")), '<html lang="bg" class="accent-explorers">')

    def test_teacher_pages_keep_school_red(self):
        self.client.force_login(make_teacher())
        self.assertContains(self.client.get(reverse("review_list")), '<html lang="bg">')


class CosmeticShopTests(TestCase):
    def setUp(self):
        self.student = make_student()
        give_coins(self.student, 20)
        self.title = Privilege.objects.get(code="title_legend")
        self.frame = Privilege.objects.get(code="frame_gold")

    def test_buying_a_title_wears_it_and_needs_no_teacher(self):
        purchase = buy_privilege(self.student, self.title)
        self.assertIsNotNone(purchase.used_at)
        self.assertNotIn(purchase, unused_purchases())
        self.student.refresh_from_db()
        self.assertEqual(self.student.shown_title, self.title)

    def test_cannot_buy_the_same_twice(self):
        buy_privilege(self.student, self.frame)
        with self.assertRaisesMessage(GameRuleError, "Вече имаш"):
            buy_privilege(self.student, self.frame)

    def test_can_wear_only_owned_items(self):
        with self.assertRaises(GameRuleError):
            wear(self.student, self.frame)
        buy_privilege(self.student, self.frame)
        wear(self.student, None, kind=Privilege.Kind.FRAME)  # сваля рамката
        self.student.refresh_from_db()
        self.assertIsNone(self.student.shown_frame)

    def test_profile_choices(self):
        buy_privilege(self.student, self.title)
        self.client.force_login(self.student)
        self.client.post(reverse("profile"), {"action": "title", "title": ""})
        self.student.refresh_from_db()
        self.assertIsNone(self.student.shown_title)
        self.client.post(reverse("profile"), {"action": "title", "title": self.title.pk})
        self.student.refresh_from_db()
        self.assertEqual(self.student.shown_title, self.title)

    def test_shop_page_sections(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("shop"))
        self.assertContains(response, "За профила")
        self.assertContains(response, "Златна рамка")
        self.assertContains(response, "frame-gold")  # преглед на рамката

    def test_title_is_shown_in_leaderboard(self):
        buy_privilege(self.student, self.title)
        self.client.force_login(make_teacher())
        self.assertContains(self.client.get(reverse("leaderboard")), '<span class="player-title">Легенда</span>', html=True)


class StreakTests(TestCase):
    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()

    def approve_weeks_ago(self, weeks):
        complete(self.teacher, self.student, title=f"Мисия {weeks}")
        Claim.objects.filter(pk=Claim.objects.latest("pk").pk).update(
            reviewed_at=timezone.now() - timedelta(weeks=weeks))

    def test_consecutive_weeks(self):
        self.assertEqual(streak_weeks(self.student), 0)
        for weeks in (0, 1, 2):
            self.approve_weeks_ago(weeks)
        self.assertEqual(streak_weeks(self.student), 3)

    def test_streak_survives_until_the_week_ends(self):
        for weeks in (1, 2):
            self.approve_weeks_ago(weeks)
        self.assertEqual(streak_weeks(self.student), 2)  # тази седмица още няма мисия

    def test_gap_breaks_the_streak(self):
        for weeks in (0, 2, 3):
            self.approve_weeks_ago(weeks)
        self.assertEqual(streak_weeks(self.student), 1)

    def test_streak_badge_and_home_chip(self):
        for weeks in (2, 1):
            self.approve_weeks_ago(weeks)
        complete(self.teacher, self.student, title="Тази седмица")  # третата седмица → значка
        self.assertTrue(StudentBadge.objects.filter(student=self.student, badge__name="Три седмици подред").exists())
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("home")), "3 седмици подред")


class WeeklyLeaderboardTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.old = make_student("star@example.com", nickname="Звезда")
        self.new = make_student("new@example.com", nickname="Новак")
        complete(self.teacher, self.old, xp=90, title="Стара")
        self.old.xp_transactions.update(created_at=timezone.now() - timedelta(weeks=3))
        complete(self.teacher, self.new, xp=30, title="Нова")

    def names(self, period):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("leaderboard"), {"period": period})
        return [row.name for row in response.context["student_rows"]], response

    def test_week_counts_only_this_week(self):
        names, _ = self.names("week")
        self.assertEqual(names[0], "Новак")
        names, _ = self.names("all")
        self.assertEqual(names[0], "Звезда")

    def test_movement_since_the_start_of_the_week(self):
        complete(self.teacher, self.new, xp=90, title="Още една")  # Новак: 120 > 90
        _, response = self.names("all")
        rows = {row.name: row for row in response.context["student_rows"]}
        self.assertEqual((rows["Новак"].rank, rows["Новак"].movement), (1, 1))
        self.assertEqual(rows["Звезда"].movement, -1)
        self.assertContains(response, "▲1")

    def test_my_row_is_shown_even_outside_the_top_50(self):
        for number in range(50):
            student = make_student(f"s{number}@example.com", nickname=f"Ученик{number}")
            complete(self.teacher, student, xp=95, title=f"М{number}")
        me = make_student("me@example.com", nickname="Аз")
        self.client.force_login(me)
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.context["my_row"].name, "Аз")

    def test_api_period(self):
        self.client.force_login(self.teacher)
        data = self.client.get("/api/leaderboard/", {"period": "week"}).json()
        self.assertEqual(data["students"][0]["name"], "Новак")
        self.assertIn("movement", data["students"][0])


class MissionCardTests(TestCase):
    def test_difficulty_by_xp(self):
        self.assertEqual([difficulty(xp, 90)["name"] for xp in (20, 50, 90)], ["Лесна", "Средна", "Трудна"])

    def test_time_left(self):
        now = timezone.now()
        self.assertEqual(time_left(now + timedelta(hours=5)), "последен ден")
        self.assertEqual(time_left(now + timedelta(hours=30)), "остават 2 дни")

    def test_cards_show_tags_and_how_many_did_it(self):
        teacher, student = make_teacher(), make_student()
        mission = make_mission(teacher, title="Скоро изтича", xp=90, days=1)
        other = make_student("drug@example.com", nickname="Друг")
        approve_claim(submit_claim(other, mission, "Готово, ето доказателството."), teacher)
        self.client.force_login(student)
        response = self.client.get(reverse("mission_list"))
        self.assertContains(response, "tier-hard")
        self.assertContains(response, "Нова")
        self.assertContains(response, "последен ден")
        self.assertContains(response, "изпълнили я 1")


class CelebrationTests(TestCase):
    def test_level_up_is_celebrated_once(self):
        teacher, student = make_teacher(), make_student()
        complete(teacher, student, xp=100)  # ниво 2 и значка „Първа мисия“
        self.client.force_login(student)
        first = self.client.get(reverse("home"))
        self.assertContains(first, 'id="celebrate"')
        self.assertContains(first, "Мина на ниво 2")
        self.assertContains(first, "celebrate.js")
        self.assertNotContains(self.client.get(reverse("home")), 'id="celebrate"')


class AppTests(TestCase):
    def test_manifest(self):
        response = self.client.get(reverse("manifest"))
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        data = json.loads(response.content)
        self.assertEqual(data["display"], "standalone")
        self.assertTrue(any(icon.get("purpose") == "maskable" for icon in data["icons"]))

    def test_service_worker_and_offline_page(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertContains(response, "/offline/")
        self.assertContains(self.client.get(reverse("offline")), "Няма връзка")

    def test_student_has_bottom_menu(self):
        self.client.force_login(make_student())
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="tabbar"')
        self.assertContains(response, 'rel="manifest"')


class LogoPreviewTests(TestCase):
    def test_logo_url_works_without_media_folder(self):
        rules = GameSettings.load()
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15"
               b"\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
        rules.school_logo = SimpleUploadedFile("logo-test.png", png, content_type="image/png")
        rules.save()
        try:
            self.assertTrue(rules.school_logo.url.startswith("/school-logo/?v="))
            self.client.force_login(User.objects.create_superuser("a@example.com", "TaynaParola123"))
            page = self.client.get(reverse("admin:economy_gamesettings_change", args=[1]))
            self.assertContains(page, "/school-logo/?v=")
            logo = self.client.get(rules.school_logo.url)
            self.assertEqual(logo.status_code, 200)
            logo.close()
        finally:
            rules.school_logo.delete(save=False)
