"""
Връзка от Django към услугата на асистента (FastAPI).

Само Django говори с асистента – браузърът никога не го вика директно.
Всяка заявка носи общия таен ключ ASSISTANT_TOKEN от .env и избрания
в admin доставчик и модел.
"""
import httpx
from django.conf import settings

from economy.models import GameSettings


class AssistantUnavailable(Exception):
    """Асистентът не можа да отговори. Текстът се показва на потребителя."""


def _headers():
    return {"X-Assistant-Token": settings.ASSISTANT_TOKEN}


def check_assistant_health():
    """
    Проверява дали услугата на асистента работи.
    Връща (True/False, съобщение за показване в admin).
    """
    try:
        response = httpx.get(f"{settings.ASSISTANT_URL}/health", headers=_headers(), timeout=2)
    except httpx.HTTPError:
        return False, "не отговаря (услугата е спряна или адресът е грешен)"

    if response.status_code == 200:
        return True, "работи"
    if response.status_code in (401, 403):
        return False, "отказва достъп – ASSISTANT_TOKEN не съвпада"
    return False, f"грешка {response.status_code}"


def call(path, payload):
    """Изпраща заявка към асистента и връща отговора (речник) или хвърля AssistantUnavailable."""
    rules = GameSettings.load()
    body = {"provider": rules.llm_provider, "model": rules.llm_model, **payload}
    try:
        response = httpx.post(f"{settings.ASSISTANT_URL}{path}", json=body, headers=_headers(),
                              timeout=settings.ASSISTANT_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        raise AssistantUnavailable("Асистентът не отговори навреме. Опитайте отново.")
    except httpx.HTTPError:
        raise AssistantUnavailable("Асистентът временно не е достъпен.")

    if response.status_code == 200:
        return response.json()
    if response.status_code == 502:
        # Грешка при езиковия модел – асистентът е върнал ясно съобщение.
        raise AssistantUnavailable(response.json().get("detail") or "Асистентът не можа да отговори.")
    if response.status_code in (401, 403, 503):
        raise AssistantUnavailable("Асистентът не е настроен правилно. Съобщете на администратора.")
    raise AssistantUnavailable(f"Асистентът върна грешка {response.status_code}.")
