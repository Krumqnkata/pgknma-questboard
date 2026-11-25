import io
import os
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.demo import content
from accounts.demo.story import FILES
from accounts.models import SchoolClass, User
from accounts.testing import make_mission, make_student, make_teacher
from badges.models import Badge
from economy.models import GameSettings
from missions.models import Claim, EvidenceFile, FileKind, Mission
from quizzes.models import Attempt, Question
from timetable.models import Lesson

MEDIA = tempfile.mkdtemp(prefix="questboard-seed-media-")


def run(command, **options):
    call_command(command, stdout=io.StringIO(), **options)


@override_settings(MEDIA_ROOT=MEDIA)
@patch.dict(os.environ, {"DEMO_PASSWORD": "DemoParola2026!"})
class SeedTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_demo_activity(self):
        run("seed_demo")
        run("seed_demo")  # второто пускане не прави дубликати
        self.assertEqual(User.objects.count(), 41)
        self.assertTrue(User.objects.filter(second_guild__isnull=False).exists())
        run("seed_activity")
        statuses = set(Claim.objects.values_list("status", flat=True))
        self.assertTrue({Claim.Status.APPROVED, Claim.Status.PENDING} <= statuses)
        self.assertTrue(Claim.objects.filter(captain__isnull=False).exists())
        self.assertTrue(Claim.objects.filter(mission__kind=Mission.Kind.HOMEWORK).exists())
        self.assertEqual(set(Attempt.objects.values_list("status", flat=True)), {"passed", "failed", "void"})
        self.assertTrue(Question.objects.filter(is_approved=False).exists())
        # Нищо не е в бъдещето и никоя проверка не е преди заявката си.
        for claim in Claim.objects.exclude(reviewed_at=None):
            self.assertLessEqual(claim.submitted_at, claim.reviewed_at)
            self.assertLessEqual(claim.reviewed_at, timezone.now())
        with self.assertRaisesMessage(CommandError, "Вече има активност"):
            run("seed_activity")

    def test_every_photo_is_real_and_credited(self):
        names = {file for quest in [*content.MISSIONS, *content.HOMEWORK] for _text, file in quest.proofs if file}
        photos = {path.name for path in FILES.glob("*.jpg")}
        self.assertEqual({name for name in names if name.endswith(".jpg")}, photos)
        credits = (FILES / "CREDITS.md").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"\| (\S+\.jpg) \|", credits)), photos)

    def test_refuses_to_mix_with_real_users(self):
        User.objects.create_user("istinski@uchilishte.bg", "TaynaParola123", role=User.Role.TEACHER)
        with self.assertRaisesMessage(CommandError, "истински потребители"):
            run("seed_activity")

    def test_reset_wipes_everything_and_seeds(self):
        rules = GameSettings.load()
        rules.school_name = "Моето училище"
        rules.save()
        teacher, student = make_teacher(), make_student(nickname="Старият")
        mission = make_mission(teacher)
        claim = Claim.objects.create(mission=mission, student=student, evidence="старо")
        old = EvidenceFile(claim=claim, kind=FileKind.IMAGE, original_name="старо.jpg", size=1)
        old.file.save("x", ContentFile(b"x"))
        old_path = Path(old.file.path)
        Badge.objects.create(name="Измислена", rule="manual", description="x")
        run("seed_demo")
        lessons = Lesson.objects.count()

        with patch("builtins.input", return_value="не"), self.assertRaisesMessage(CommandError, "Нищо не е изтрито"):
            run("reset_demo")
        self.assertTrue(Claim.objects.filter(evidence="старо").exists())

        with patch("builtins.input", return_value="ИЗТРИЙ"), self.captureOnCommitCallbacks(execute=True):
            run("reset_demo")
        self.assertFalse(Claim.objects.filter(evidence="старо").exists())
        self.assertFalse(User.objects.exclude(email__endswith=content.DOMAIN).exists())
        self.assertFalse(Badge.objects.filter(name="Измислена").exists())
        self.assertFalse(old_path.exists())
        self.assertEqual(GameSettings.load().school_name, "Моето училище")  # настройките остават
        self.assertEqual(Lesson.objects.count(), lessons)                   # и разписанието
        self.assertTrue(SchoolClass.objects.filter(name="12А").exists())
        for file in EvidenceFile.objects.all():
            self.assertTrue(Path(file.file.path).exists())
