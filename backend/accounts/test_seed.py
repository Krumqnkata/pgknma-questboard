import io
import os
import shutil
import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import User
from missions.models import Claim

MEDIA = tempfile.mkdtemp(prefix="questboard-seed-media-")


@override_settings(MEDIA_ROOT=MEDIA)
@patch.dict(os.environ, {"DEMO_PASSWORD": "DemoParola2026!"})
class SeedActivityTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_demo_activity(self):
        call_command("seed_demo", stdout=io.StringIO())
        call_command("seed_activity", stdout=io.StringIO())
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 20)
        self.assertTrue(Claim.objects.filter(status=Claim.Status.APPROVED).exists())
        self.assertTrue(Claim.objects.filter(status=Claim.Status.PENDING).exists())
        self.assertTrue(Claim.objects.filter(files__isnull=False).exists())

    def test_refuses_to_mix_with_real_users(self):
        User.objects.create_user("istinski@uchilishte.bg", "TaynaParola123", role=User.Role.TEACHER)
        with self.assertRaisesMessage(CommandError, "истински потребители"):
            call_command("seed_activity", stdout=io.StringIO())
