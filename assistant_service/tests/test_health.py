"""Тестове за защитата на услугата с тайния ключ."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
from main import app

client = TestClient(app)


@patch.object(config, "ASSISTANT_TOKEN", "test-token")
class HealthTokenTests(unittest.TestCase):
    def test_correct_token_is_accepted(self):
        response = client.get("/health", headers={"X-Assistant-Token": "test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_missing_token_is_rejected(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 401)

    def test_wrong_token_is_rejected(self):
        response = client.get("/health", headers={"X-Assistant-Token": "wrong-token"})
        self.assertEqual(response.status_code, 401)


class NoTokenConfiguredTests(unittest.TestCase):
    @patch.object(config, "ASSISTANT_TOKEN", "")
    def test_service_refuses_when_token_not_configured(self):
        response = client.get("/health", headers={"X-Assistant-Token": ""})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
