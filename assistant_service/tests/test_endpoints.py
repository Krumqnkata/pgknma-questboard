"""
Тестове на адресите на асистента с тестовия модел (без интернет и без ключ).
Проверяват кода около модела: формати, проверки, грешки.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import config
from main import app
from providers import ProviderError, ToolCall

client = TestClient(app)
HEADERS = {"X-Assistant-Token": "test-token"}
MISSION = {"title": "Репортаж", "description": "Направи репортаж за събитие.", "criteria": "Връзка към статия."}
GUILDS = [{"name": "Builders"}, {"name": "Explorers"}]
TOOLS = [{
    "name": "free_rooms",
    "description": "Свободни кабинети",
    "parameters": {"type": "object", "properties": {"day": {"type": "string"}, "period": {"type": "string"}},
                   "required": ["day", "period"], "additionalProperties": False},
}]


@patch.object(config, "ASSISTANT_TOKEN", "test-token")
@patch.object(config, "ALLOW_FAKE", True)
class EndpointTests(unittest.TestCase):
    def post(self, path, body):
        return client.post(path, json=body, headers=HEADERS)

    def test_hint(self):
        response = self.post("/hint", {"provider": "fake", "mission": MISSION})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["hint"])

    def test_draft_is_valid_and_uses_known_guild(self):
        response = self.post("/mission-draft", {"provider": "fake", "idea": "Помощ в библиотеката",
                                                "guilds": GUILDS, "max_xp": 100})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["guild"], ["Builders", "Explorers"])

    def test_draft_xp_is_limited_by_game_rules(self):
        response = self.post("/mission-draft", {"provider": "fake", "idea": "Помощ в библиотеката",
                                                "guilds": GUILDS, "max_xp": 25})
        self.assertEqual(response.json()["xp"], 25)  # тестовият модел предлага 40

    def test_draft_with_unknown_guild_is_rejected(self):
        bad = {"title": "Мисия", "description": "Описание на мисията", "criteria": "Критерий",
               "guild": "Пирати", "xp": 30}
        with patch("providers.fake.FakeProvider.json", return_value=bad):
            response = self.post("/mission-draft", {"provider": "fake", "idea": "идея за мисия", "guilds": GUILDS,
                                                    "max_xp": 100})
        self.assertEqual(response.status_code, 502)

    def test_draft_with_missing_fields_is_rejected(self):
        with patch("providers.fake.FakeProvider.json", return_value={"title": "Само заглавие"}):
            response = self.post("/mission-draft", {"provider": "fake", "idea": "идея за мисия", "guilds": GUILDS,
                                                    "max_xp": 100})
        self.assertEqual(response.status_code, 502)

    def test_plan_chooses_tool(self):
        response = self.post("/query/plan", {"provider": "fake", "question": "free_rooms сега?", "tools": TOOLS})
        self.assertEqual(response.json()["tool"], "free_rooms")

    def test_plan_answers_with_text_when_no_tool_fits(self):
        response = self.post("/query/plan", {"provider": "fake", "question": "Колко е часът?", "tools": TOOLS})
        self.assertIsNone(response.json()["tool"])
        self.assertTrue(response.json()["answer"])

    def test_plan_rejects_tool_that_was_not_offered(self):
        with patch("providers.fake.FakeProvider.choose_tool", return_value=ToolCall("delete_everything")):
            response = self.post("/query/plan", {"provider": "fake", "question": "?", "tools": TOOLS})
        self.assertEqual(response.status_code, 502)

    def test_answer(self):
        response = self.post("/query/answer", {"provider": "fake", "question": "Свободни кабинети?",
                                               "tool": "free_rooms", "data": {"rooms": ["101"]}})
        self.assertEqual(response.status_code, 200)

    def test_model_error_gives_clear_message(self):
        with patch("providers.fake.FakeProvider.text", side_effect=ProviderError("Claude не отговори навреме.")):
            response = self.post("/hint", {"provider": "fake", "mission": MISSION})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Claude не отговори навреме.")

    def test_missing_api_key_gives_clear_message(self):
        with patch.dict(config.LLM_API_KEYS, {"claude": ""}):
            response = self.post("/hint", {"provider": "claude", "mission": MISSION})
        self.assertEqual(response.status_code, 502)
        self.assertIn("липсва API ключ", response.json()["detail"])

    def test_every_endpoint_requires_token(self):
        for path in ("/hint", "/mission-draft", "/query/plan", "/query/answer"):
            with self.subTest(path=path):
                self.assertEqual(client.post(path, json={}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
