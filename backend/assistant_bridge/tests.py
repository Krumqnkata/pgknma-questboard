from unittest.mock import patch

import httpx
from django.test import TestCase

from .client import check_assistant_health


class AssistantHealthTests(TestCase):
    """Индикаторът в admin трябва да казва ясно какво е състоянието на асистента."""

    @patch("assistant_bridge.client.httpx.get")
    def test_running_assistant(self, fake_get):
        fake_get.return_value = httpx.Response(200, json={"status": "ok"})
        self.assertEqual(check_assistant_health(), (True, "работи"))

    @patch("assistant_bridge.client.httpx.get", side_effect=httpx.ConnectError("спрян"))
    def test_stopped_assistant(self, fake_get):
        ok, message = check_assistant_health()
        self.assertFalse(ok)
        self.assertIn("не отговаря", message)

    @patch("assistant_bridge.client.httpx.get")
    def test_wrong_token(self, fake_get):
        fake_get.return_value = httpx.Response(401)
        ok, message = check_assistant_health()
        self.assertFalse(ok)
        self.assertIn("ASSISTANT_TOKEN", message)
