"""
Тестов „модел“ без интернет и без ключ. Ползва се само в автоматичните тестове
(включва се с ASSISTANT_ALLOW_FAKE=1). Отговаря предвидимо, за да се проверява кодът около модела.
"""
from .base import LLMProvider, ToolCall


class FakeProvider(LLMProvider):
    def __init__(self, api_key="", model=""):
        self.model = model or "fake"

    def text(self, system, user):
        return "Започни, като прочетеш внимателно критерия и си направиш кратък план на стъпките."

    def json(self, system, user, schema):
        guild = schema["properties"]["guild"]["enum"][0]
        return {
            "title": "Помощ в училищната библиотека",
            "description": "Помогни при подреждането на новите книги в училищната библиотека.",
            "criteria": "Библиотекарят потвърждава, че си помагал поне един час.",
            "guild": guild,
            "xp": 40,
            "is_group": True,
            "team_min": 1,
            "team_max": 50,
            "badge": schema["properties"]["badge"]["enum"][-1],
        }

    def choose_tool(self, system, user, tools):
        # Ако името на справка се среща във въпроса – избира нея, иначе отговаря с текст.
        for tool in tools:
            if tool.name in user:
                arguments = {name: "" for name in tool.parameters.get("properties", {})}
                return ToolCall(name=tool.name, arguments=arguments)
        return "Мога да помогна със справки по разписанието."
