"""OpenAI през официалната библиотека openai."""
import json

import openai

from .base import TIMEOUT_SECONDS, LLMProvider, ProviderError, ToolCall, connection_error, status_error, timeout_error


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        if not model:
            raise ProviderError("Задайте име на модела на OpenAI в настройките на играта.")
        # Без повторен опит – иначе потребителят би чакал двойно повече.
        self.client = openai.OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
        self.model = model

    def _create(self, system, user, **kwargs):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **kwargs,
            )
        except openai.APITimeoutError:
            raise timeout_error(self.model)
        except openai.APIConnectionError:
            raise connection_error("OpenAI")
        except openai.APIStatusError as error:
            raise status_error("OpenAI", self.model, error.status_code, error.message)
        return response.choices[0].message

    def text(self, system, user):
        return (self._create(system, user).content or "").strip()

    def json(self, system, user, schema):
        message = self._create(system, user, response_format={
            "type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True},
        })
        if getattr(message, "refusal", None):
            raise ProviderError("Моделът отказа да отговори на тази заявка.")
        return json.loads(message.content)

    def choose_tool(self, system, user, tools):
        message = self._create(system, user, tools=[
            {"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters, "strict": True,
            }} for t in tools
        ])
        if message.tool_calls:
            call = message.tool_calls[0].function
            return ToolCall(name=call.name, arguments=json.loads(call.arguments or "{}"))
        return (message.content or "").strip()
