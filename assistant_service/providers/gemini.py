"""Google Gemini през официалната библиотека google-genai."""
import json

import httpx
from google import genai
from google.genai import errors, types

from .base import TIMEOUT_SECONDS, LLMProvider, ProviderError, ToolCall, connection_error, status_error, timeout_error


class GeminiProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        if not model:
            raise ProviderError("Задайте име на модела на Gemini в настройките на играта.")
        # Времето за чакане е в милисекунди.
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000))
        self.model = model

    def _generate(self, user, config):
        try:
            return self.client.models.generate_content(model=self.model, contents=user, config=config)
        except errors.APIError as error:
            raise status_error("Gemini", self.model, error.code, error.message)
        except httpx.TimeoutException:
            raise timeout_error(self.model)
        except (httpx.HTTPError, OSError):
            raise connection_error("Gemini")

    def text(self, system, user):
        response = self._generate(user, types.GenerateContentConfig(system_instruction=system))
        return (response.text or "").strip()

    def json(self, system, user, schema):
        response = self._generate(user, types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_json_schema=schema,
        ))
        return json.loads(response.text)

    def choose_tool(self, system, user, tools):
        declarations = [types.FunctionDeclaration(name=t.name, description=t.description,
                                                  parameters_json_schema=t.parameters) for t in tools]
        response = self._generate(user, types.GenerateContentConfig(
            system_instruction=system, tools=[types.Tool(function_declarations=declarations)],
        ))
        if response.function_calls:
            call = response.function_calls[0]
            return ToolCall(name=call.name, arguments=dict(call.args or {}))
        return (response.text or "").strip()
