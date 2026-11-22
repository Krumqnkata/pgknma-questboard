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


NAMES = dict(GameSettings.LlmProvider.choices)


def provider_keys():
    """За кои доставчици има API ключ в .env на асистента: {"gemini": True, ...}. Празно, ако не работи."""
    try:
        response = httpx.get(f"{settings.ASSISTANT_URL}/health", headers=_headers(), timeout=2)
    except httpx.HTTPError:
        return {}
    return response.json().get("providers", {}) if response.status_code == 200 else {}


def check_assistant_health(provider=None):
    """
    Проверява дали услугата на асистента работи и има ли ключ за избрания доставчик.
    Връща (True/False, съобщение за показване в admin).
    """
    try:
        response = httpx.get(f"{settings.ASSISTANT_URL}/health", headers=_headers(), timeout=2)
    except httpx.HTTPError:
        return False, "не отговаря (услугата е спряна или адресът е грешен)"

    if response.status_code in (401, 403):
        return False, "отказва достъп – ASSISTANT_TOKEN не съвпада"
    if response.status_code != 200:
        return False, f"грешка {response.status_code}"
    if not provider:
        return True, "работи"
    name = NAMES.get(provider, provider)
    if not response.json().get("providers", {}).get(provider):
        return False, f"работи, но в .env няма API ключ за {name}"
    return True, f"работи · има API ключ за {name}"


def check_model():
    """
    Бутонът „Провери асистента“: една кратка заявка към избрания модел.
    Връща (True/False, съобщение) – при грешка и оригиналния текст на доставчика.
    """
    choice = GameSettings.load().assistant_model()
    label = f"{NAMES.get(choice['provider'], choice['provider'])} · {choice['model']}"
    try:
        response = httpx.post(f"{settings.ASSISTANT_URL}/check", json=choice, headers=_headers(),
                              timeout=settings.ASSISTANT_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        return False, f"{label}: асистентът не отговори навреме."
    except httpx.HTTPError:
        return False, "Услугата на асистента не отговаря. Пуснете я със start.py."
    if response.status_code in (401, 403):
        return False, "Услугата на асистента отказва достъп – ASSISTANT_TOKEN не съвпада."
    if response.status_code != 200:
        return False, f"Услугата на асистента върна грешка {response.status_code}."

    result = response.json()
    if result.get("ok"):
        return True, f"{label} работи – отговори за {result.get('seconds', 0)} s: „{result.get('answer', '')}“"
    detail = f" (отговор на доставчика: {result['detail']})" if result.get("detail") else ""
    return False, f"{label}: {result.get('error')}{detail}"


def call(path, payload, model=None):
    """
    Изпраща заявка към асистента и връща отговора (речник) или хвърля AssistantUnavailable.
    model – по желание друг доставчик и модел {"provider", "model"} (за контролните случаи).
    """
    body = {**(model or GameSettings.load().assistant_model()), **payload}
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
