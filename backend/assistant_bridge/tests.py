"""
Тестове на асистента от страната на Django. Услугата на асистента е заменена
с подставка (mock), затова тестовете не ползват интернет и езиков модел.
"""
import re
from pathlib import Path
from unittest.mock import patch

import httpx
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.testing import make_mission, make_student, make_teacher
from economy.models import GameSettings, Privilege, Purchase
from missions.services import GameRuleError
from timetable.importer import import_timetable

from .client import AssistantUnavailable, check_assistant_health
from .models import AssistantLog, Hint
from .pseudonyms import TeacherCodes
from .services import AssistantError, ask, draft_mission, request_hint

SAMPLE = Path(settings.BASE_DIR) / "timetable" / "sample" / "razpisanie_primer.csv"


class AssistantHealthTests(TestCase):
    """Индикаторът в admin трябва да казва ясно какво е състоянието на асистента."""

    @patch("assistant_bridge.client.httpx.get")
    def test_running_assistant(self, fake_get):
        fake_get.return_value = httpx.Response(200, json={"status": "ok",
                                                          "providers": {"claude": True, "openai": False}})
        ok, message = check_assistant_health()
        self.assertTrue(ok)
        self.assertIn("Claude ✓", message)
        self.assertIn("OpenAI ✗", message)

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


class PseudonymTests(TestCase):
    def setUp(self):
        self.codes = TeacherCodes(["Елена Маринова", "Петър Николов"])

    def test_names_are_hidden_in_question(self):
        hidden = self.codes.hide("Кога е свободна Маринова? А Петър Николов?")
        self.assertNotIn("Маринова", hidden)
        self.assertNotIn("Николов", hidden)
        self.assertIn("Учител-", hidden)

    def test_answer_gets_names_back(self):
        code = self.codes.name_to_code["Елена Маринова"]
        self.assertEqual(self.codes.reveal(f"{code} е свободна."), "Елена Маринова е свободна.")

    def test_data_is_hidden(self):
        data = self.codes.hide_data({"lessons": [{"teacher": "Петър Николов", "room": "203"}]})
        self.assertNotIn("Петър Николов", str(data))
        self.assertEqual(data["lessons"][0]["room"], "203")


class HintTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.mission = make_mission(self.teacher)
        self.token = Purchase.objects.create(student=self.student, price_paid=2,
                                             privilege=Privilege.objects.get(code="hint_token"))

    @patch("assistant_bridge.client.call", return_value={"hint": "Започни от критерия."})
    def test_hint_spends_one_token(self, fake_call):
        hint = request_hint(self.student, self.mission)
        self.assertEqual(hint.text, "Започни от критерия.")
        self.token.refresh_from_db()
        self.assertTrue(self.token.is_used)
        self.assertEqual(AssistantLog.objects.get().success, True)

    @patch("assistant_bridge.client.call")
    def test_only_mission_text_is_sent(self, fake_call):
        fake_call.return_value = {"hint": "насока"}
        request_hint(self.student, self.mission)
        payload = fake_call.call_args.args[1]
        self.assertNotIn(self.student.nickname, str(payload))
        self.assertNotIn(self.student.email, str(payload))

    @patch("assistant_bridge.client.call", side_effect=AssistantUnavailable("Асистентът не отговори навреме."))
    def test_token_is_not_spent_on_error(self, fake_call):
        with self.assertRaises(AssistantError):
            request_hint(self.student, self.mission)
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_used)
        self.assertFalse(AssistantLog.objects.get().success)

    def test_no_token(self):
        self.token.delete()
        with self.assertRaises(GameRuleError):
            request_hint(self.student, self.mission)

    def test_teacher_can_forbid_hints(self):
        self.mission.hints_allowed = False
        self.mission.save()
        with self.assertRaises(GameRuleError):
            request_hint(self.student, self.mission)

    def test_disabled_assistant(self):
        rules = GameSettings.load()
        rules.assistant_enabled = False
        rules.save()
        with self.assertRaises(AssistantError):
            request_hint(self.student, self.mission)
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_used)

    @patch("assistant_bridge.client.call", return_value={"hint": "насока"})
    def test_daily_limit(self, fake_call):
        rules = GameSettings.load()
        rules.assistant_daily_limit = 1
        rules.save()
        request_hint(self.student, self.mission)
        Purchase.objects.create(student=self.student, price_paid=2, privilege=self.token.privilege)
        with self.assertRaises(AssistantError):
            request_hint(self.student, self.mission)

    @patch("assistant_bridge.client.call", return_value={"hint": "насока"})
    def test_hint_through_the_page(self, fake_call):
        self.client.force_login(self.student)
        response = self.client.post(reverse("mission_hint", args=[self.mission.pk]), follow=True)
        self.assertContains(response, "насока")
        self.assertEqual(Hint.objects.count(), 1)


class DraftTests(TestCase):
    DRAFT = {"title": "Коледен базар", "description": "Помогни при подготовката на базара.",
             "criteria": "Класният ръководител потвърждава участието.", "guild": "Citizens", "xp": 40}

    def setUp(self):
        self.teacher = make_teacher()

    @patch("assistant_bridge.client.call")
    def test_draft_fills_form_data(self, fake_call):
        fake_call.return_value = self.DRAFT
        draft = draft_mission(self.teacher, "Учениците да помогнат за базара")
        self.assertEqual(draft["title"], "Коледен базар")
        self.assertIsNotNone(draft["guild"])

    @patch("assistant_bridge.client.call")
    def test_draft_page_does_not_publish(self, fake_call):
        fake_call.return_value = self.DRAFT
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission_create"), {"draft_idea": "Помощ за коледния базар"})
        self.assertContains(response, "Коледен базар")
        self.assertContains(response, "Прегледайте и редактирайте")
        from missions.models import Mission
        self.assertFalse(Mission.objects.exists())

    @patch("assistant_bridge.client.call", side_effect=AssistantUnavailable("Асистентът временно не е достъпен."))
    def test_draft_error_keeps_form_working(self, fake_call):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("mission_create"), {"draft_idea": "Помощ за коледния базар"})
        self.assertContains(response, "Асистентът временно не е достъпен.")
        self.assertContains(response, "Публикувай")

    def test_student_cannot_draft(self):
        with self.assertRaises(GameRuleError):
            draft_mission(make_student(), "Някаква идея за мисия")


class AskTests(TestCase):
    def setUp(self):
        import_timetable(SAMPLE.read_text(encoding="utf-8"))
        self.teacher = make_teacher()

    def test_teacher_question_runs_report_with_hidden_names(self):
        sent = []

        def fake_call(path, payload):
            sent.append(payload)
            if path == "/query/plan":
                # Моделът връща кода на учителя, който е видял във въпроса.
                code = re.search(r"Учител-\d+", payload["question"]).group()
                return {"tool": "teacher_schedule", "arguments": {"teacher": code, "day": "понеделник"}}
            data = payload["data"]
            return {"answer": f"{data['teacher']} има {len(data['lessons'])} часа."}

        with patch("assistant_bridge.client.call", side_effect=fake_call):
            answer = ask(self.teacher, "Какви часове има Маринова в понеделник?")

        self.assertNotIn("Маринова", str(sent))         # моделът не вижда името
        self.assertEqual(answer.tool, "teacher_schedule")
        self.assertIn("Елена Маринова има", answer.text)  # кодът е върнат обратно в име

    @patch("assistant_bridge.client.call",
           return_value={"tool": "free_rooms", "arguments": {"day": "сряда", "period": "3"}})
    def test_student_cannot_get_teacher_report_even_if_model_picks_it(self, fake_call):
        answer = ask(make_student(), "Кои кабинети са свободни?")
        self.assertIn("не е достъпна", answer.text)

    def test_student_tools_are_limited(self):
        from .tools import tools_for
        names = {tool["name"] for tool in tools_for(make_student())}
        self.assertEqual(names, {"class_schedule", "my_progress"})

    @patch("assistant_bridge.client.call", return_value={"tool": None, "answer": "Мога да помогна със справки."})
    def test_plain_answer_without_report(self, fake_call):
        self.assertEqual(ask(self.teacher, "Здравей").text, "Мога да помогна със справки.")

    def test_ask_api_reports_disabled_assistant(self):
        rules = GameSettings.load()
        rules.assistant_enabled = False
        rules.save()
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("api-assistant-ask"), {"question": "Кои кабинети са свободни?"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertIn("изключен", response.json()["detail"])

    def test_chat_page_opens(self):
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("assistant")), "assistant-chat.js")


class EvaluationCommandTests(TestCase):
    """Командата с контролните случаи – с подставка вместо истински модел."""

    def fake_call(self, path, payload, providers=None):
        if path == "/hint":
            return {"hint": "Започни, като прочетеш внимателно условието."}
        if path == "/mission-draft":
            return {"title": "Мисия", "description": "Описание", "criteria": "Критерий", "guild": "Builders", "xp": 40}
        # Справка: връща първата позволена справка – някои случаи ще са „неуспешни“, и това е очаквано.
        return {"tool": payload["tools"][0]["name"], "arguments": {}}

    def test_command_writes_report(self):
        import io
        import tempfile

        from django.core.management import call_command

        from .management.commands import evaluate_assistant

        with tempfile.TemporaryDirectory() as folder, \
                patch.object(evaluate_assistant, "REPORT", Path(folder) / "report.md"), \
                patch("assistant_bridge.client.call", side_effect=self.fake_call):
            call_command("evaluate_assistant", stdout=io.StringIO())
            report = (Path(folder) / "report.md").read_text(encoding="utf-8")
        self.assertIn("Резултат:", report)
        self.assertIn("| H1 | подсказка | ✓ |", report)
        self.assertIn("| D1 | чернова | ✓ |", report)

    def test_each_provider_separately(self):
        import io
        import tempfile

        from django.core.management import call_command

        from .management.commands import evaluate_assistant

        rules = GameSettings.load()
        rules.gemini_model = "gemini-модел"
        rules.save()
        with tempfile.TemporaryDirectory() as folder,                 patch.object(evaluate_assistant, "REPORT", Path(folder) / "report.md"),                 patch("assistant_bridge.client.call", side_effect=self.fake_call) as fake:
            call_command("evaluate_assistant", "--provider", "all", stdout=io.StringIO())
            reports = sorted(path.name for path in Path(folder).iterdir())
        # OpenAI няма модел в настройките – пропуснат е.
        self.assertEqual(reports, ["assistant-evaluation-claude.md", "assistant-evaluation-gemini.md"])
        self.assertEqual(fake.call_args.args[2], [{"provider": "gemini", "model": "gemini-модел"}])


class ProviderOrderTests(TestCase):
    """Трите доставчика заедно: основният първи, после резервните."""

    def test_primary_first_then_others(self):
        rules = GameSettings.load()
        rules.llm_provider = "gemini"
        rules.gemini_model, rules.openai_model, rules.claude_model = "gemini-модел", "openai-модел", "claude-opus-5-5"
        order = [p["provider"] for p in rules.provider_order()]
        self.assertEqual(order[0], "gemini")
        self.assertEqual(set(order), {"gemini", "openai", "claude"})

    def test_provider_without_model_is_skipped(self):
        rules = GameSettings.load()  # по подразбиране само Claude има модел
        self.assertEqual([p["provider"] for p in rules.provider_order()], ["claude"])

    def test_only_primary_when_fallback_is_off(self):
        rules = GameSettings.load()
        rules.openai_model = "openai-модел"
        rules.use_other_providers = False
        self.assertEqual(len(rules.provider_order()), 1)

    @patch("assistant_bridge.client.httpx.post")
    def test_order_is_sent_to_assistant(self, fake_post):
        from . import client
        fake_post.return_value = httpx.Response(200, json={"hint": "насока", "provider": "claude"})
        client.call("/hint", {"mission": {}})
        self.assertEqual(fake_post.call_args.kwargs["json"]["providers"][0]["provider"], "claude")

    @patch("assistant_bridge.client.call", return_value={"hint": "насока", "provider": "gemini"})
    def test_log_records_which_model_answered(self, fake_call):
        student = make_student()
        mission = make_mission(make_teacher())
        Purchase.objects.create(student=student, price_paid=2, privilege=Privilege.objects.get(code="hint_token"))
        request_hint(student, mission)
        self.assertEqual(AssistantLog.objects.get().provider, "gemini")
