"""Снимки и PDF към доказателството: проверка, запис, кой ги вижда."""
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import User
from accounts.testing import make_mission, make_student, make_teacher
from economy.models import GameSettings

from .models import Claim, EvidenceFile
from .services import GameRuleError, submit_claim

MEDIA = tempfile.mkdtemp(prefix="questboard-test-media-")


def photo(name="snimka.jpg", size=(3000, 2000), mode="RGB", fmt="JPEG", gps=True):
    """Снимка като от телефон – голяма и с EXIF (включително GPS)."""
    image = Image.new(mode, size, (200, 30, 40) if mode == "RGB" else (200, 30, 40, 120))
    buffer = BytesIO()
    if gps and fmt == "JPEG":
        exif = Image.Exif()
        exif[0x0110] = "Телефон"          # модел
        exif[0x8825] = {2: (42.0, 41.0, 0.0)}  # GPS
        image.save(buffer, fmt, exif=exif.tobytes())
    else:
        image.save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def pdf(name="otchet.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class EvidenceFileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.teacher, self.student = make_teacher(), make_student()
        self.mission = make_mission(self.teacher)

    def submit(self, files, text=""):
        return submit_claim(self.student, self.mission, text, files)

    def test_photo_is_shrunk_and_hidden_data_removed(self):
        claim = self.submit([photo()])
        record = claim.files.get()
        self.assertEqual(record.kind, "image")
        self.assertEqual(record.original_name, "snimka.jpg")
        with record.file.open("rb") as stored, Image.open(stored) as image:
            self.assertEqual(max(image.size), 1600)
            self.assertEqual(len(image.getexif()), 0)  # няма EXIF – нито модел, нито GPS
        self.assertNotIn("snimka", record.file.name)  # случайно име на диска

    def test_png_with_transparency_and_pdf(self):
        claim = self.submit([photo("ekran.png", (800, 600), "RGBA", "PNG"), pdf()])
        self.assertEqual(sorted(claim.files.values_list("kind", flat=True)), ["image", "pdf"])

    def test_text_alone_or_file_alone_is_enough(self):
        self.assertTrue(self.submit([pdf()]).pk)
        with self.assertRaisesMessage(GameRuleError, "текст, връзка или файл"):
            submit_claim(make_student("b@example.com", nickname="Друг"), self.mission, "", [])

    def test_fake_image_is_refused(self):
        fake = SimpleUploadedFile("virus.jpg", b"MZ\x90\x00 not an image", content_type="image/jpeg")
        with self.assertRaisesMessage(GameRuleError, "не може да се качи"):
            self.submit([fake])
        self.assertFalse(Claim.objects.exists())  # нищо не се записва, ако един файл е невалиден

    def test_limits_from_settings(self):
        rules = GameSettings.load()
        rules.evidence_max_files, rules.evidence_max_mb = 1, 1
        rules.save()
        with self.assertRaisesMessage(GameRuleError, "Най-много 1 файла"):
            self.submit([pdf("a.pdf"), pdf("b.pdf")])
        big = SimpleUploadedFile("big.pdf", b"%PDF-" + b"0" * (1024 * 1024 + 1), content_type="application/pdf")
        with self.assertRaisesMessage(GameRuleError, "по-голям от 1 MB"):
            self.submit([big])
        rules.evidence_max_files = 0
        rules.save()
        with self.assertRaisesMessage(GameRuleError, "изключено"):
            self.submit([pdf()])

    def test_resubmission_replaces_old_files(self):
        from economy.services import reject_claim

        claim = self.submit([photo()])
        old_name = claim.files.get().file.name
        reject_claim(claim, self.teacher, "Снимката е размазана.")
        with self.captureOnCommitCallbacks(execute=True):
            claim = self.submit([pdf()], "Ето отчета.")
        self.assertEqual(list(claim.files.values_list("kind", flat=True)), ["pdf"])
        self.assertFalse(EvidenceFile.objects.filter(file=old_name).exists())
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists(old_name))  # и файлът от диска е изтрит

    def test_who_can_open_the_file(self):
        record = self.submit([photo()]).files.get()
        url = reverse("evidence_file", args=[record.pk])
        stranger = make_student("drug@example.com", nickname="Друг")
        other_teacher = make_teacher("drug.uchitel@example.com")
        admin = User.objects.create_superuser("a@example.com", "TaynaParola123")
        for user, status in ((self.student, 200), (self.teacher, 200), (admin, 200), (stranger, 404), (other_teacher, 404)):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, status)
                if status == 200:
                    self.assertEqual(response["Content-Type"], "image/jpeg")
                    self.assertEqual(response["Content-Security-Policy"], "sandbox")
                    response.close()
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)  # без вход – към страницата за вход

    def test_upload_through_the_mission_page(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("mission_detail", args=[self.mission.pk]))
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, "За видео сложи връзка")
        response = self.client.post(reverse("mission_detail", args=[self.mission.pk]),
                                    {"evidence": "", "files": [photo(), pdf()]}, follow=True)
        self.assertContains(response, "Заявката е изпратена")
        self.assertContains(response, "evidence-thumb")
        self.assertContains(response, "otchet.pdf")

    def test_teacher_sees_files_in_review_list(self):
        self.submit([photo()])
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("review_list")), "evidence-thumb")

    def test_api_upload(self):
        self.client.force_login(self.student)
        response = self.client.post(f"/api/missions/{self.mission.pk}/claim/",
                                    {"evidence": "Снимка от събитието", "files": [photo()]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["files"][0]["kind"], "image")
        self.assertTrue(response.json()["files"][0]["url"].startswith("/evidence/"))

    def test_api_json_still_works(self):
        self.client.force_login(self.student)
        response = self.client.post(f"/api/missions/{self.mission.pk}/claim/", {"evidence": "Връзка към статия"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["files"], [])
