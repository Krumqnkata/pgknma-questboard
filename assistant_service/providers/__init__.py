"""Избор на доставчик по име. Ключът се взема от .env на асистента."""
import config

from .base import LLMProvider, ProviderError, ToolCall  # noqa: F401

NAMES = {"openai": "OpenAI", "gemini": "Gemini", "claude": "Claude"}


def get_provider(name, model=""):
    if name == "fake":
        if not config.ALLOW_FAKE:
            raise ProviderError("Тестовият модел е изключен.")
        from .fake import FakeProvider
        return FakeProvider(model=model)

    key = config.LLM_API_KEYS.get(name, "")
    if not key:
        raise ProviderError(f"Асистентът не е настроен: липсва API ключ за {NAMES.get(name, name)}.")

    # Библиотеката на доставчика се зарежда само когато е нужна.
    if name == "claude":
        from .claude import ClaudeProvider
        return ClaudeProvider(key, model)
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(key, model)
    if name == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(key, model)
    raise ProviderError(f"Непознат доставчик: {name}")
