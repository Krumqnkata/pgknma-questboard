"""Google Gemini през официалната библиотека google-genai."""
import json

from google import genai
from google.genai import errors, types

from .base import LLMProvider, ProviderError, ToolCall


class GeminiProvider(LLMProvider):
    def __init__(self, api_key, model=""):
        if not model:
            raise ProviderError("Задайте име на модела на Gemini в настройките на играта.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def _generate(self, user, config):
        try:
            return self.client.models.generate_content(model=self.model, contents=user, config=config)
        except errors.ClientError as error:
            if error.code in (401, 403):
                raise ProviderError("Невалиден API ключ за Gemini.")
            if error.code == 429:
                raise ProviderError("Твърде много заявки към Gemini. Опитайте след малко.")
            raise ProviderError(f"Gemini върна грешка {error.code}.")
        except errors.APIError as error:
            raise ProviderError(f"Gemini върна грешка {error.code}.")
        except OSError:
            raise ProviderError("Няма връзка с Gemini.")

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
