"""OpenAI през Responses API – без истински заявки."""
import unittest
from types import SimpleNamespace as Item
from unittest.mock import MagicMock

import httpx
import openai

from providers.base import ProviderError
from providers.openai_provider import OpenAIProvider

TOOL = Item(name="shop", description="Магазинът", parameters={
    "type": "object", "properties": {}, "required": [], "additionalProperties": False})


def provider(model="gpt-6-luna", output=(), output_text=""):
    result = OpenAIProvider("sk-test", model)
    result.client = MagicMock()
    result.client.responses.create.return_value = Item(output=list(output), output_text=output_text)
    return result


def sent(target):
    return target.client.responses.create.call_args.kwargs


class OpenAIProviderTests(unittest.TestCase):
    def test_tool_call(self):
        target = provider(output=[Item(type="reasoning"), Item(type="function_call", name="shop", arguments='{"a": "1"}')])
        call = target.choose_tool("правила", "въпрос", [TOOL])
        self.assertEqual((call.name, call.arguments), ("shop", {"a": "1"}))
        tool = sent(target)["tools"][0]
        self.assertEqual((tool["type"], tool["name"], tool["strict"]), ("function", "shop", True))
        self.assertEqual(sent(target)["reasoning"], {"effort": "low"})
        self.assertFalse(sent(target)["store"])

    def test_answer_without_a_tool(self):
        message = Item(type="message", content=[Item(type="output_text")])
        self.assertEqual(provider(output=[message], output_text=" Здравей ").choose_tool("п", "в", [TOOL]), "Здравей")

    def test_json(self):
        target = provider(output_text='{"title": "Подкаст"}')
        self.assertEqual(target.json("п", "в", {"type": "object"}), {"title": "Подкаст"})
        self.assertTrue(sent(target)["text"]["format"]["strict"])

    def test_models_without_reasoning_get_no_effort(self):
        target = provider(model="gpt-4.1-mini", output_text="да")
        target.text("п", "в")
        self.assertNotIn("reasoning", sent(target))

    def test_refusal(self):
        message = Item(type="message", content=[Item(type="refusal")])
        with self.assertRaisesRegex(ProviderError, "отказа"):
            provider(output=[message]).text("п", "в")

    def test_error_text_is_for_the_admin_only(self):
        target = provider()
        error = openai.BadRequestError("тайна подробност", response=httpx.Response(
            400, request=httpx.Request("POST", "https://api.openai.com")), body=None)
        target.client.responses.create.side_effect = error
        with self.assertRaises(ProviderError) as caught:
            target.text("п", "в")
        self.assertNotIn("тайна", str(caught.exception))
        self.assertIn("тайна", caught.exception.detail)


class PlainTextTests(unittest.TestCase):
    def test_no_long_dashes(self):
        from logic import plain

        self.assertEqual(plain("Подсказка — 2 монети"), "Подсказка - 2 монети")
