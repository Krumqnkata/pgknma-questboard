"""
Общият интерфейс към езиковите модели.

Всеки доставчик (OpenAI, Gemini, Claude) има собствен файл с клас, който
прави същите три неща. Останалият код не знае кой доставчик се ползва –
затова той може да се смени от Django admin без промяна в кода.
"""
from dataclasses import dataclass, field


class ProviderError(Exception):
    """Грешка при езиковия модел. Текстът се показва на потребителя."""


@dataclass
class ToolCall:
    """Справката, която моделът е избрал, и параметрите ѝ."""

    name: str
    arguments: dict = field(default_factory=dict)


class LLMProvider:
    """Трите действия, които асистентът иска от модела."""

    def text(self, system: str, user: str) -> str:
        """Свободен текстов отговор (подсказка, оформяне на справка)."""
        raise NotImplementedError

    def json(self, system: str, user: str, schema: dict) -> dict:
        """Отговор във фиксиран JSON формат (чернова на мисия)."""
        raise NotImplementedError

    def choose_tool(self, system: str, user: str, tools: list) -> ToolCall | str:
        """Извикване на функции: моделът избира справка или отговаря с текст."""
        raise NotImplementedError
