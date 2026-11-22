from django.test import TestCase
from django.urls import reverse

from accounts.testing import make_mission, make_student, make_teacher
from economy.services import approve_claim, reject_claim
from missions.services import submit_claim

from .models import Notification


class NotificationTests(TestCase):
    """Известия при потвърдена или отказана заявка и при ново ниво (Ф15)."""

    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()

    def claim(self, xp=50, title="Мисия"):
        mission = make_mission(self.teacher, title=title, xp=xp)
        return submit_claim(self.student, mission, "Готово, ето доказателството.")

    def test_approved_claim_notifies_the_student(self):
        approve_claim(self.claim(title="Озеленяване"), self.teacher, "Браво!")
        note = self.student.notifications.get(kind=Notification.Kind.CLAIM_APPROVED)
        self.assertIn("„Озеленяване“ е потвърдена: +50 XP", note.text)
        self.assertIn("Браво!", note.text)
        self.assertFalse(note.is_read)

    def test_new_level_is_announced(self):
        approve_claim(self.claim(xp=100), self.teacher)  # 100 XP = ниво 2
        note = self.student.notifications.get(kind=Notification.Kind.LEVEL_UP)
        self.assertEqual(note.text, "Мина на ниво 2 – чирак!")

    def test_no_level_message_without_new_level(self):
        approve_claim(self.claim(xp=20), self.teacher)
        self.assertFalse(self.student.notifications.filter(kind=Notification.Kind.LEVEL_UP).exists())

    def test_rejected_claim_notifies_the_student(self):
        reject_claim(self.claim(), self.teacher, "Липсва снимка.")
        note = self.student.notifications.get(kind=Notification.Kind.CLAIM_REJECTED)
        self.assertIn("Липсва снимка.", note.text)
        self.assertIn("подадеш отново", note.text)

    def test_bell_shows_unread_count_and_page_marks_them_read(self):
        approve_claim(self.claim(xp=20), self.teacher)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("home")), 'class="bell-count"')

        response = self.client.get(reverse("notifications"))
        self.assertContains(response, "е потвърдена")
        self.assertContains(response, 'class="new-label"')  # беше непрочетено при отварянето
        self.assertNotContains(response, 'class="bell-count"')
        self.assertFalse(self.student.notifications.filter(read_at__isnull=True).exists())

    def test_teacher_has_no_bell_and_cannot_open_the_page(self):
        self.client.force_login(self.teacher)
        self.assertNotContains(self.client.get(reverse("review_list")), "icon-button bell")
        self.assertEqual(self.client.get(reverse("notifications")).status_code, 403)

    def test_students_see_only_their_own(self):
        other = make_student("drug@example.com", nickname="Друг")
        approve_claim(self.claim(xp=20), self.teacher)
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse("notifications")), "е потвърдена")

    def test_api(self):
        approve_claim(self.claim(xp=20), self.teacher)
        self.client.force_login(self.student)
        data = self.client.get("/api/notifications/").json()
        self.assertEqual(data["unread"], 2)  # потвърдена заявка + значка „Първа мисия“
        self.assertEqual({item["kind"] for item in data["items"]}, {"claim_approved", "badge"})
        self.assertEqual(self.client.post("/api/notifications/read-all/").json(), {"marked": 2})
        self.assertEqual(self.client.get("/api/notifications/").json()["unread"], 0)
