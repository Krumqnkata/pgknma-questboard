"""
Връзка от Django към услугата на асистента (FastAPI).

Само Django говори с асистента – браузърът никога не го вика директно.
Всяка заявка носи общия таен ключ ASSISTANT_TOKEN от .env и реда на
доставчиците от admin (основният първи, после резервните).
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
        keys = response.json().get("providers", {})
        names = {"claude": "Claude", "openai": "OpenAI", "gemini": "Gemini"}
        listed = ", ".join(f"{names.get(n, n)} {'✓' if ok else '✗'}" for n, ok in keys.items())
        return True, f"работи · API ключове: {listed}" if listed else "работи"
    if response.status_code in (401, 403):
        return False, "отказва достъп – ASSISTANT_TOKEN не съвпада"
    return False, f"грешка {response.status_code}"


def call(path, payload, providers=None):
    """
    Изпраща заявка към асистента и връща отговора (речник) или хвърля AssistantUnavailable.
    providers – по желание друг ред на доставчиците (напр. само един за контролните случаи).
    """
    order = providers or GameSettings.load().provider_order()
    if not order:
        raise AssistantUnavailable("Асистентът не е настроен: в настройките няма модел за нито един доставчик.")
    body = {"providers": order, **payload}
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
