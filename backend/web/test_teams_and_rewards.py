"""Отборни мисии, заместници, награди от мисия, външни контрибутори, нива в магазина и файлове."""
import io
import tempfile
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guild, User
from accounts.testing import make_mission, make_student, make_teacher
from badges.models import Badge, StudentBadge
from badges.services import award_badges, progress_for
from economy.awards import recent_awards
from economy.models import CoinTransaction, Privilege, Purchase, Sponsor, XPTransaction
from economy.services import (
    approve_claim, buy_privilege, give_bonus, owned_cosmetics, pending_claims_for, reject_claim, undo_approval,
    unused_purchases, xp_total,
)
from missions.evidence import prepare
from missions.models import Claim, MissionFile
from missions.services import GameRuleError, leave_team, parse_nicknames, submit_claim


def office_file(name="Доклад.docx", part="word/document.xml", extra=()):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in ("[Content_Types].xml", part, *extra):
            archive.writestr(path, "<x/>")
    return SimpleUploadedFile(name, buffer.getvalue())


class Base(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.deputy = make_teacher("zamestnik@example.com")
        self.captain = make_student()
        self.mate = make_student("mate@example.com", "Комета")
        self.third = make_student("third@example.com", "Вихър")
        self.mission = make_mission(self.teacher, is_group=True, team_min=2, team_max=3)

    def give_coins(self, student, amount):
        CoinTransaction.objects.create(student=student, amount=amount, kind=CoinTransaction.Kind.CORRECTION, reason="тест")

    def submit(self, *mates):
        return submit_claim(self.captain, self.mission, "Готово", teammates=mates)


class TeamTests(Base):
    def test_parse_nicknames(self):
        self.assertEqual(parse_nicknames(" Комета, Вихър;Комета,, "), ["Комета", "Вихър"])

    def test_approval_rewards_the_whole_team(self):
        claim = self.submit("Комета", "Вихър")
        result = approve_claim(claim, self.teacher)
        self.assertEqual(result.team, 2)
        for student in (self.captain, self.mate, self.third):
            self.assertEqual(xp_total(student), 50)
            self.assertEqual(progress_for(student).missions, 1)  # значките и сериите броят и съотборниците

    def test_only_the_captain_claim_waits_for_decision(self):
        claim = self.submit("Комета")
        self.assertEqual(list(pending_claims_for(self.teacher)), [claim])
        with self.assertRaises(GameRuleError):
            approve_claim(claim.team.get(), self.teacher)
        self.assertEqual(xp_total(self.mate), 0)

    def test_team_size_and_unknown_nicknames(self):
        for mates in ([], ["Комета", "Вихър", "Никой"], ["Никой"], ["Феникс"]):
            with self.assertRaises(GameRuleError):
                self.submit(*mates)
        self.assertFalse(Claim.objects.exists())

    def test_a_student_is_in_one_team_only(self):
        self.submit("Комета")
        other = make_student("other@example.com", "Искра")
        with self.assertRaises(GameRuleError):
            submit_claim(other, self.mission, "Готово", teammates=["Комета"])
        with self.assertRaises(GameRuleError):
            submit_claim(self.mate, self.mission, "Готово", teammates=["Вихър"])
        self.assertEqual(Claim.objects.count(), 2)

    def test_teammates_are_refused_for_individual_missions(self):
        with self.assertRaises(GameRuleError):
            submit_claim(self.captain, make_mission(self.teacher), "Готово", teammates=["Комета"])

    def test_leaving_the_team(self):
        claim = self.submit("Комета", "Вихър")
        leave_team(self.mate, self.mission)
        approve_claim(claim, self.teacher)
        self.assertEqual(xp_total(self.mate), 0)
        with self.assertRaises(GameRuleError):  # след решението вече не може
            leave_team(self.third, self.mission)
        with self.assertRaises(GameRuleError):  # капитанът не напуска
            leave_team(self.captain, self.mission)

    def test_rejected_team_can_submit_again_with_other_people(self):
        claim = self.submit("Комета")
        reject_claim(claim, self.teacher, "Липсва снимка")
        self.assertEqual(Claim.objects.get(student=self.mate).status, Claim.Status.REJECTED)
        claim = self.submit("Вихър")
        approve_claim(claim, self.teacher)
        self.assertEqual([xp_total(s) for s in (self.captain, self.mate, self.third)], [50, 0, 50])

    def test_rejected_teammate_can_become_captain(self):
        reject_claim(self.submit("Комета"), self.teacher)
        claim = submit_claim(self.mate, self.mission, "Наново", teammates=["Феникс"])
        self.assertIsNone(claim.captain_id)
        approve_claim(claim, self.teacher)
        self.assertEqual([xp_total(self.captain), xp_total(self.mate)], [50, 50])

    def test_undo_takes_back_from_the_whole_team(self):
        claim = self.submit("Комета", "Вихър")
        approve_claim(claim, self.teacher)
        undo_approval(self.teacher, claim.team.get(student=self.third), "не е участвал")  # само един
        self.assertEqual([xp_total(s) for s in (self.captain, self.mate, self.third)], [50, 50, 0])
        undo_approval(self.teacher, claim, "грешка")
        self.assertEqual([xp_total(s) for s in (self.captain, self.mate, self.third)], [0, 0, 0])

    def test_mission_rules_for_teams(self):
        for low, high in ((1, 3), (4, 3), (2, 50)):
            self.mission.team_min, self.mission.team_max = low, high
            with self.assertRaises(ValidationError):
                self.mission.clean()

    def test_pages(self):
        self.client.force_login(self.captain)
        url = reverse("mission_detail", args=[self.mission.pk])
        self.assertContains(self.client.get(url), 'name="teammates"')
        response = self.client.post(url, {"evidence": "Мой текст", "teammates": "Никой"})
        self.assertContains(response, "Няма ученик с псевдоним")
        self.assertContains(response, "Мой текст")  # написаното не се губи
        self.client.post(url, {"evidence": "Готово", "teammates": "Комета"})
        self.client.force_login(self.mate)
        self.assertContains(self.client.get(url), "Напусни отбора")
        self.client.post(reverse("team_leave", args=[self.mission.pk]))
        self.assertFalse(Claim.objects.filter(student=self.mate).exists())

    def test_teammate_sees_the_captain_file_but_others_do_not(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            claim = submit_claim(self.captain, self.mission, "", [office_file()], ["Комета"])
            url = claim.files.get().get_absolute_url()
            for user, status in ((self.captain, 200), (self.mate, 200), (self.teacher, 200), (self.third, 404),
                                 (self.deputy, 404)):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, status, user)
                response.close()

    def test_api(self):
        self.client.force_login(self.captain)
        response = self.client.post(f"/api/missions/{self.mission.pk}/claim/",
                                    {"evidence": "Готово", "teammates": "Комета"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Claim.objects.get(student=self.mate).captain_id, response.json()["id"])


class ReviewerTests(Base):
    def test_deputy_can_review_only_when_chosen(self):
        claim = self.submit("Комета")
        self.assertFalse(pending_claims_for(self.deputy).exists())
        with self.assertRaises(GameRuleError):
            approve_claim(claim, self.deputy)
        self.mission.reviewers.add(self.deputy)
        self.assertEqual(list(pending_claims_for(self.deputy)), [claim])
        approve_claim(claim, self.deputy)
        self.assertEqual(xp_total(self.captain), 50)

    def test_deputy_sees_but_does_not_edit(self):
        self.mission.reviewers.add(self.deputy)
        self.client.force_login(self.deputy)
        page = self.client.get(reverse("mission_detail", args=[self.mission.pk]))
        self.assertNotContains(page, reverse("mission_edit", args=[self.mission.pk]))
        self.assertEqual(self.client.get(reverse("mission_edit", args=[self.mission.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("mission_list")), "заместник на")
        self.assertEqual(self.client.patch(f"/api/missions/{self.mission.pk}/", {"title": "Друго"},
                                           content_type="application/json").status_code, 404)

    def test_student_chosen_by_mistake_cannot_review(self):
        self.mission.reviewers.add(self.third)
        with self.assertRaises(GameRuleError):
            approve_claim(self.submit("Комета"), self.third)

    def test_teacher_chooses_a_deputy_in_the_form(self):
        self.client.force_login(self.teacher)
        deadline = timezone.localtime(timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        data = {"title": "Нова", "description": "Описание", "criteria": "Критерий", "xp": 30, "deadline": deadline,
                "guild": Guild.objects.first().pk, "reviewers": [self.deputy.pk], "hints_allowed": "on"}
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.client.post(reverse("mission_create"), {**data, "files": [office_file("Указания.docx")]})
            mission = self.teacher.created_missions.get(title="Нова")
            self.assertEqual(list(mission.reviewers.all()), [self.deputy])
            record = mission.files.get()
            self.client.force_login(self.captain)
            response = self.client.get(record.get_absolute_url())
            self.assertIn("attachment", response["Content-Disposition"])
            response.close()
            self.client.force_login(self.teacher)
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("mission_edit", args=[mission.pk]), {
                    **data, "is_active": "on", "remove_files": [record.pk]})
            self.assertFalse(MissionFile.objects.exists())
        self.assertNotIn(self.teacher, self.client.get(
            reverse("mission_create")).context["form"].fields["reviewers"].queryset)


class MissionRewardTests(Base):
    def setUp(self):
        super().setUp()
        self.badge = Badge.objects.get(name="Екипен дух")
        self.title = Privilege.objects.get(code="title_discoverer")
        self.mission.reward_badge, self.mission.reward_item = self.badge, self.title
        self.mission.save()

    def test_everyone_in_the_team_gets_the_rewards_and_undo_takes_them(self):
        claim = self.submit("Комета")
        approve_claim(claim, self.teacher)
        for student in (self.captain, self.mate):
            student.refresh_from_db()
            self.assertTrue(StudentBadge.objects.filter(student=student, badge=self.badge).exists())
            self.assertEqual(student.shown_title, self.title)
            self.assertEqual(progress_for(student).purchases, 0)  # не се брои за покупка
        undo_approval(self.teacher, claim, "грешка")
        for student in (self.captain, self.mate):
            student.refresh_from_db()
            self.assertFalse(StudentBadge.objects.filter(student=student, badge=self.badge).exists())
            self.assertIsNone(student.shown_title)
            self.assertFalse(owned_cosmetics(student).exists())

    def test_mission_badge_and_item_cannot_be_got_otherwise(self):
        self.assertNotIn(self.badge, award_badges(self.captain))
        self.give_coins(self.captain, 50)
        with self.assertRaises(GameRuleError):
            buy_privilege(self.captain, self.title)
        self.client.force_login(self.captain)
        self.assertNotContains(self.client.get(reverse("shop")), "Откривател")

    def test_stock_is_not_exceeded(self):
        ticket = Privilege.objects.create(code="ticket", kind=Privilege.Kind.SPONSOR, name="Билет", price=5, stock=1,
                                          sponsor=Sponsor.objects.create(name="Театър"))
        self.mission.reward_item = ticket
        self.mission.save()
        approve_claim(self.submit("Комета"), self.teacher)
        self.assertEqual(Purchase.objects.filter(privilege=ticket).count(), 1)
        self.assertEqual(xp_total(self.mate), 50)  # XP се дава и без предмета

    def test_recent_awards(self):
        approve_claim(self.submit("Комета"), self.teacher)
        give_bonus(self.teacher, self.third, 10, "Помощ")
        awards = recent_awards(20)
        self.assertEqual({award.kind for award in awards}, {"значка", "бонус", "награда"})
        self.assertIn("+10 XP", [award.text for award in awards])
        self.client.force_login(self.captain)
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Последни награди в училище")
        self.assertNotContains(page, "Помощ")  # причината за чужд бонус не се показва


class ShopTests(Base):
    def test_sponsor_reward_has_limited_stock_and_is_handed_over(self):
        ticket = Privilege.objects.create(code="ticket", kind=Privilege.Kind.SPONSOR, name="Билет за театър", price=5,
                                          stock=1, sponsor=Sponsor.objects.create(name="Театър"))
        self.give_coins(self.captain, 10)
        self.give_coins(self.mate, 10)
        purchase = buy_privilege(self.captain, ticket)
        self.assertIn(purchase, unused_purchases(self.teacher))
        with self.assertRaises(GameRuleError):
            buy_privilege(self.mate, ticket)
        self.client.force_login(self.mate)
        self.assertContains(self.client.get(reverse("shop")), "Изчерпана")
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("purchase_list")), "Отбележи като предадена")

    def test_cosmetics_unlock_with_the_level(self):
        item = Privilege.objects.get(code="title_strategist")
        self.assertEqual(item.min_level, 3)
        self.give_coins(self.captain, 20)
        with self.assertRaises(GameRuleError):
            buy_privilege(self.captain, item)
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(reverse("shop")), "Отключва се на ниво 3")
        XPTransaction.objects.create(student=self.captain, amount=250, reason="тест")
        buy_privilege(self.captain, item)
        self.assertIn(item, owned_cosmetics(self.captain))

    def test_only_the_responsible_teacher_hands_it_over(self):
        ticket = Privilege.objects.create(code="ticket", kind=Privilege.Kind.SPONSOR, name="Билет", price=5,
                                          sponsor=Sponsor.objects.create(name="Театър"), responsible=self.teacher)
        purchase = Purchase.objects.create(student=self.captain, privilege=ticket, price_paid=5)
        other = make_teacher("other-teacher@example.com")
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse("purchase_list")), "Билет")
        self.client.post(reverse("purchase_use", args=[purchase.pk]))
        purchase.refresh_from_db()
        self.assertFalse(purchase.is_used)
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(reverse("shop")), "Предава: " + self.teacher.get_full_name())
        self.teacher.is_active = False  # отговорникът е напуснал: предава всеки учител
        self.teacher.save()
        self.client.force_login(other)
        self.assertContains(self.client.get(reverse("purchase_list")), "Билет")
        self.client.post(reverse("purchase_use", args=[purchase.pk]))
        purchase.refresh_from_db()
        self.assertTrue(purchase.is_used)

    def test_responsible_is_required(self):
        with self.assertRaisesMessage(ValidationError, "отговорник"):
            Privilege(code="x", kind=Privilege.Kind.SPONSOR, name="Книга", price=1,
                      sponsor=Sponsor.objects.create(name="Театър")).clean()

    def test_sponsor_is_required(self):
        with self.assertRaises(ValidationError):
            Privilege(code="x", kind=Privilege.Kind.SPONSOR, name="Книга", price=1).clean()

    def test_unknown_sponsor_logo_is_not_found(self):
        self.assertEqual(self.client.get(reverse("sponsor_logo", args=["x.png"])).status_code, 404)


class OfficeFileTests(TestCase):
    def test_kinds(self):
        for part, kind in (("word/document.xml", "docx"), ("xl/workbook.xml", "xlsx"), ("ppt/presentation.xml", "pptx")):
            self.assertEqual(prepare(office_file(part=part), 10**6).kind, kind)

    def test_macros_other_archives_and_fakes_are_refused(self):
        for upload in (office_file(extra=["word/vbaProject.bin"]), office_file(part="virus.exe"),
                       SimpleUploadedFile("a.docx", b"PK\x03\x04broken")):
            with self.assertRaises(GameRuleError):
                prepare(upload, 10**6)


class SystemCheckTests(Base):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user("admin@example.com", "TaynaParola123", role=User.Role.ADMIN, is_staff=True,
                                              is_superuser=True)
        self.old = make_mission(self.teacher, title="Стара")
        self.old.deadline = timezone.now() - timedelta(days=5)
        self.old.save()

    def test_only_admin(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("system_check")).status_code, 302)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("system_check")), "Активни мисии с изтекъл срок")

    def test_nothing_changes_without_the_button(self):
        self.client.force_login(self.admin)
        with patch("assistant_bridge.client.call", return_value={"answer": "Първо спрете мисиите.", "provider": "x"}) as call:
            self.assertContains(self.client.post(reverse("system_check"), {"explain": "1"}), "Първо спрете мисиите.")
        sent = str(call.call_args)
        for secret in (self.captain.nickname, self.captain.email, self.old.title):
            self.assertNotIn(secret, sent)
        self.old.refresh_from_db()
        self.assertTrue(self.old.is_active)

    def test_fix(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("system_check"), {"fix": "expired_missions"})
        self.old.refresh_from_db()
        self.mission.refresh_from_db()
        self.assertFalse(self.old.is_active)
        self.assertTrue(self.mission.is_active)

    def test_every_fix(self):
        self.mission.reviewers.add(self.third)  # ученик
        self.captain.shown_title = Privilege.objects.get(code="title_legend")
        self.captain.save()
        Privilege.objects.create(code="t", kind=Privilege.Kind.SPONSOR, name="Билет", price=1, stock=0,
                                 sponsor=Sponsor.objects.create(name="Кино"))
        self.client.force_login(self.admin)
        for code in ("wrong_reviewers", "wrong_look", "sold_out", "няма-такъв"):
            self.client.post(reverse("system_check"), {"fix": code})
        self.captain.refresh_from_db()
        self.assertIsNone(self.captain.shown_title)
        self.assertFalse(self.mission.reviewers.exists())
        self.assertFalse(Privilege.objects.get(code="t").is_active)

    def test_dashboard_shows_recent_awards(self):
        give_bonus(self.teacher, self.third, 10, "Помощ при концерта")
        self.client.force_login(self.admin)
        page = self.client.get(reverse("admin:index"))
        self.assertContains(page, "Последни награди")
        self.assertContains(page, "Помощ при концерта")


class WidgetTests(Base):
    def test_assistant_popup_and_cookie_note(self):
        self.assertContains(self.client.get(reverse("login")), "data-cookie-note")
        self.assertNotContains(self.client.get(reverse("login")), "assistant-popup")
        self.client.force_login(self.captain)
        self.assertContains(self.client.get(reverse("shop")), 'id="assistant-popup"')
        self.assertNotContains(self.client.get(reverse("assistant")), 'id="assistant-popup"')

    def test_popup_is_hidden_when_the_assistant_is_off(self):
        from economy.models import GameSettings

        rules = GameSettings.load()
        rules.assistant_enabled = False
        rules.save()
        self.client.force_login(self.captain)
        self.assertNotContains(self.client.get(reverse("shop")), "assistant-popup")

    def test_privacy_page_describes_the_cookies(self):
        page = self.client.get(reverse("privacy"))
        for text in ('id="cookies"', "csrftoken", "отборът му при отборна мисия"):
            self.assertContains(page, text)
