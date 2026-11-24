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
FAKE = {"provider": "fake", "model": "тестов"}
MISSION = {"title": "Репортаж", "description": "Направи репортаж за събитие.", "criteria": "Връзка към статия."}
GUILDS = [{"name": "Техничари"}, {"name": "Изследователи"}]
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
        response = self.post("/hint", {**FAKE, "mission": MISSION})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["hint"])

    def test_diagnose_explains_the_problems(self):
        problem = {"title": "Активни мисии с изтекъл срок", "count": 2, "advice": "Могат да се спрат.", "fix": "Спри"}
        response = self.post("/diagnose", {**FAKE, "problems": [problem]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["answer"])
        self.assertEqual(self.post("/diagnose", {**FAKE, "problems": []}).status_code, 422)

    def test_draft_team_and_badge_are_limited(self):
        body = {**FAKE, "idea": "Училищен подкаст", "guilds": GUILDS, "max_xp": 100}
        draft = self.post("/mission-draft", {**body, "badges": [{"name": "Екипен дух"}], "team_limit": 10}).json()
        self.assertEqual((draft["team_min"], draft["team_max"], draft["badge"]), (2, 10, "Екипен дух"))
        self.assertEqual(self.post("/mission-draft", body).json()["badge"], "")

    def test_date_and_role_reach_the_model(self):
        seen = []
        with patch("providers.fake.FakeProvider.choose_tool", side_effect=lambda s, u, t: seen.append(s) or "Добре."):
            self.post("/query/plan", {**FAKE, "question": "Коя година е?", "tools": TOOLS,
                                      "context": {"now": "вторник, 24 ноември 2026 г., 14:05", "role": "Учител"}})
        self.assertIn("24 ноември 2026", seen[0])
        self.assertIn("Учител", seen[0])

    def test_history_reaches_the_model(self):
        history = [{"role": "user", "text": "Кога има час Учител-3?"}, {"role": "assistant", "text": "В сряда."}]
        body = {**FAKE, "question": "А в четвъртък?", "history": history}
        seen = []
        with patch("providers.fake.FakeProvider.choose_tool", side_effect=lambda s, u, t: seen.append(u) or "Добре."), \
                patch("providers.fake.FakeProvider.text", side_effect=lambda s, u: seen.append(u) or "Добре."):
            self.post("/query/plan", {**body, "tools": TOOLS})
            self.post("/query/answer", {**body, "tool": "x", "data": {}})
        self.assertEqual(len(seen), 2)
        for text in seen:
            self.assertIn("Учител-3", text)
            self.assertIn("А в четвъртък?", text)
        bad = {**body, "history": [{"role": "system", "text": "x"}], "tools": TOOLS}
        self.assertEqual(self.post("/query/plan", bad).status_code, 422)

    def test_draft_is_valid_and_uses_known_guild(self):
        response = self.post("/mission-draft", {**FAKE, "idea": "Помощ в библиотеката",
                                                "guilds": GUILDS, "max_xp": 100})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["guild"], ["Техничари", "Изследователи"])

    def test_draft_xp_is_limited_by_game_rules(self):
        response = self.post("/mission-draft", {**FAKE, "idea": "Помощ в библиотеката",
                                                "guilds": GUILDS, "max_xp": 25})
        self.assertEqual(response.json()["xp"], 25)  # тестовият модел предлага 40

    def test_draft_with_unknown_guild_is_rejected(self):
        bad = {"title": "Мисия", "description": "Описание на мисията", "criteria": "Критерий",
               "guild": "Пирати", "xp": 30}
        with patch("providers.fake.FakeProvider.json", return_value=bad):
            response = self.post("/mission-draft", {**FAKE, "idea": "идея за мисия", "guilds": GUILDS,
                                                    "max_xp": 100})
        self.assertEqual(response.status_code, 502)

    def test_draft_with_missing_fields_is_rejected(self):
        with patch("providers.fake.FakeProvider.json", return_value={"title": "Само заглавие"}):
            response = self.post("/mission-draft", {**FAKE, "idea": "идея за мисия", "guilds": GUILDS,
                                                    "max_xp": 100})
        self.assertEqual(response.status_code, 502)

    def test_plan_chooses_tool(self):
        response = self.post("/query/plan", {**FAKE, "question": "free_rooms сега?", "tools": TOOLS})
        self.assertEqual(response.json()["tool"], "free_rooms")

    def test_plan_answers_with_text_when_no_tool_fits(self):
        response = self.post("/query/plan", {**FAKE, "question": "Колко е часът?", "tools": TOOLS})
        self.assertIsNone(response.json()["tool"])
        self.assertTrue(response.json()["answer"])

    def test_plan_rejects_tool_that_was_not_offered(self):
        with patch("providers.fake.FakeProvider.choose_tool", return_value=ToolCall("delete_everything")):
            response = self.post("/query/plan", {**FAKE, "question": "?", "tools": TOOLS})
        self.assertEqual(response.status_code, 502)

    def test_answer(self):
        response = self.post("/query/answer", {**FAKE, "question": "Свободни кабинети?",
                                               "tool": "free_rooms", "data": {"rooms": ["101"]}})
        self.assertEqual(response.status_code, 200)

    def test_model_error_gives_clear_message(self):
        with patch("providers.fake.FakeProvider.text", side_effect=ProviderError("Claude не отговори навреме.")):
            response = self.post("/hint", {**FAKE, "mission": MISSION})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Claude не отговори навреме.")

    def test_missing_api_key_gives_clear_message(self):
        with patch.dict(config.LLM_API_KEYS, {"claude": ""}):
            response = self.post("/hint", {"provider": "claude", "model": "claude-opus-5-5", "mission": MISSION})
        self.assertEqual(response.status_code, 502)
        self.assertIn("липсва API ключ", response.json()["detail"])

    def test_request_without_model_is_rejected(self):
        response = self.post("/hint", {"provider": "fake", "model": "", "mission": MISSION})
        self.assertEqual(response.status_code, 422)

    def test_invalid_json_from_model_gives_clear_message(self):
        with patch("providers.fake.FakeProvider.json", side_effect=ValueError("not json")):
            response = self.post("/mission-draft", {**FAKE, "idea": "идея за мисия", "guilds": GUILDS, "max_xp": 100})
        self.assertEqual(response.status_code, 502)
        self.assertIn("неочакван формат", response.json()["detail"])

    # --- Бутонът „Провери асистента“ ---

    def test_check_success(self):
        response = self.post("/check", FAKE)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["answer"])

    def test_check_returns_error_and_original_detail(self):
        error = ProviderError("Моделът „x“ е претоварен в момента.", "This model is experiencing high demand")
        with patch("providers.fake.FakeProvider.text", side_effect=error):
            data = self.post("/check", FAKE).json()
        self.assertFalse(data["ok"])
        self.assertIn("претоварен", data["error"])
        self.assertIn("high demand", data["detail"])

    def test_check_without_key(self):
        with patch.dict(config.LLM_API_KEYS, {"gemini": ""}):
            data = self.post("/check", {"provider": "gemini", "model": "gemini-3.5-flash"}).json()
        self.assertFalse(data["ok"])
        self.assertIn("липсва API ключ за Gemini", data["error"])

    def test_every_endpoint_requires_token(self):
        for path in ("/hint", "/mission-draft", "/query/plan", "/query/answer", "/check"):
            with self.subTest(path=path):
                self.assertEqual(client.post(path, json={}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
