"""
OpenAI през официалната библиотека openai (Responses API).

Новите модели (напр. gpt-6-luna) извикват функции само през Responses API: в по-стария
Chat Completions това работи единствено с изключено разсъждаване.
"""
import json

import openai

from .base import TIMEOUT_SECONDS, LLMProvider, ProviderError, ToolCall, connection_error, status_error, timeout_error

# Само тези модели разсъждават и приемат настройката за усилие; другите връщат грешка.
REASONING_MODELS = ("gpt-5", "gpt-6", "o1", "o3", "o4")


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        if not model:
            raise ProviderError("Задайте име на модела на OpenAI в настройките на играта.")
        # Без повторен опит – иначе потребителят би чакал двойно повече.
        self.client = openai.OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
        self.model = model

    def _create(self, system, user, **kwargs):
        if self.model.startswith(REASONING_MODELS):
            # Ниско усилие – отговорите са кратки и трябва да идват бързо.
            kwargs["reasoning"] = {"effort": "low"}
        try:
            # store=False – разговорът не се пази при OpenAI за по-късно извикване.
            response = self.client.responses.create(
                model=self.model, instructions=system, input=user, store=False, **kwargs)
        except openai.APITimeoutError:
            raise timeout_error(self.model)
        except openai.APIConnectionError:
            raise connection_error("OpenAI")
        except openai.APIStatusError as error:
            raise status_error("OpenAI", self.model, error.status_code, error.message)
        for item in response.output:
            if item.type == "message" and any(part.type == "refusal" for part in item.content):
                raise ProviderError("Моделът отказа да отговори на тази заявка.")
        return response

    def text(self, system, user):
        return (self._create(system, user).output_text or "").strip()

    def json(self, system, user, schema):
        response = self._create(system, user, text={
            "format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True},
        })
        return json.loads(response.output_text)

    def choose_tool(self, system, user, tools):
        response = self._create(system, user, tools=[
            {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters, "strict": True}
            for t in tools
        ])
        for item in response.output:
            if item.type == "function_call":
                return ToolCall(name=item.name, arguments=json.loads(item.arguments or "{}"))
        return (response.output_text or "").strip()
