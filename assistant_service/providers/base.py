"""
Общият интерфейс към езиковите модели.

Всеки доставчик (OpenAI, Gemini, Claude) има собствен файл с клас, който
прави същите три неща. Останалият код не знае кой доставчик се ползва –
затова той може да се смени от Django admin без промяна в кода.
"""
from dataclasses import dataclass, field


class ProviderError(Exception):
    """
    Грешка при езиковия модел. Текстът се показва на потребителя.
    detail е оригиналното съобщение на доставчика – вижда го само администраторът.
    """

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


# Колко секунди се чака отговор от модела. Django чака асистента малко повече.
TIMEOUT_SECONDS = 40


def status_error(name, model, code, detail=""):
    """Превръща кода на грешка от доставчика в ясно съобщение на български."""
    detail = str(detail or "")[:300]
    if code == 401 or (code == 400 and "api key" in detail.lower()):
        message = f"Невалиден API ключ за {name}. Проверете ключа в .env и рестартирайте асистента."
    elif code == 403:
        message = f"Ключът за {name} няма достъп до модела „{model}“."
    elif code == 404:
        message = f"Моделът „{model}“ не съществува или не е достъпен с този ключ. Проверете името на модела."
    elif code == 429:
        message = f"Твърде много заявки към {name} или е изчерпан лимитът на ключа. Опитайте след малко."
    elif code in (500, 502, 503, 529):
        message = f"Моделът „{model}“ е претоварен в момента. Опитайте след малко или изберете друг модел."
    elif code == 504:
        message = f"Моделът „{model}“ не отговори навреме. Опитайте отново или изберете по-бърз модел."
    else:
        message = f"{name} върна грешка {code}."
    return ProviderError(message, detail)


def timeout_error(model):
    return ProviderError(f"Моделът „{model}“ не отговори за {TIMEOUT_SECONDS} секунди. "
                         "Опитайте отново или изберете по-бърз модел.")


def connection_error(name):
    return ProviderError(f"Няма връзка с {name}. Проверете интернета на сървъра.")


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
