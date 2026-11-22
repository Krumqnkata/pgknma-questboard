"""Anthropic Claude през официалната библиотека anthropic."""
import json

import anthropic

from .base import TIMEOUT_SECONDS, LLMProvider, ProviderError, ToolCall, connection_error, status_error, timeout_error

DEFAULT_MODEL = "claude-opus-5-5"

# При тези модели, ако моделът откаже по съображения за безопасност, API-то
# само повтаря заявката с подходящ резервен модел (server-side fallback).
MODELS_WITH_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5"}


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        # Без повторен опит – иначе потребителят би чакал двойно повече.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
        self.model = model or DEFAULT_MODEL

    def _create(self, output_config=None, **kwargs):
        # Ниско усилие (effort) – отговорите са кратки и трябва да идват бързо.
        params = {"model": self.model, "max_tokens": 8000,
                  "output_config": {"effort": "low", **(output_config or {})}, **kwargs}
        try:
            if self.model in MODELS_WITH_FALLBACK:
                response = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
            else:
                response = self.client.messages.create(**params)
        except anthropic.APIStatusError as error:
            raise status_error("Claude", self.model, error.status_code, error.message)
        except anthropic.APITimeoutError:
            raise timeout_error(self.model)
        except anthropic.APIConnectionError:
            raise connection_error("Claude")

        if response.stop_reason == "refusal":
            raise ProviderError("Моделът отказа да отговори на тази заявка.")
        return response

    @staticmethod
    def _text_of(response):
        return "\n".join(block.text for block in response.content if block.type == "text").strip()

    def text(self, system, user):
        return self._text_of(self._create(system=system, messages=[{"role": "user", "content": user}]))

    def json(self, system, user, schema):
        response = self._create(
            system=system, messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        return json.loads(self._text_of(response))

    def choose_tool(self, system, user, tools):
        response = self._create(
            system=system, messages=[{"role": "user", "content": user}],
            tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True}
                   for t in tools],
        )
        for block in response.content:
            if block.type == "tool_use":
                return ToolCall(name=block.name, arguments=dict(block.input))
        return self._text_of(response)
