"""Anthropic Claude през официалната библиотека anthropic."""
import json

import anthropic

from .base import LLMProvider, ProviderError, ToolCall

DEFAULT_MODEL = "claude-opus-5-5"

# При тези модели, ако моделът откаже по съображения за безопасност, API-то
# само повтаря заявката с подходящ резервен модел (server-side fallback).
MODELS_WITH_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5"}


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        self.client = anthropic.Anthropic(api_key=api_key, timeout=25.0, max_retries=1)
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
        except anthropic.AuthenticationError:
            raise ProviderError("Невалиден API ключ за Claude.")
        except anthropic.RateLimitError:
            raise ProviderError("Твърде много заявки към Claude. Опитайте след малко.")
        except anthropic.APIStatusError as error:
            raise ProviderError(f"Claude върна грешка {error.status_code}.")
        except anthropic.APITimeoutError:
            raise ProviderError("Claude не отговори навреме.")
        except anthropic.APIConnectionError:
            raise ProviderError("Няма връзка с Claude.")

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
