"""
Връзка от Django към услугата на асистента (FastAPI).

Само Django говори с асистента – браузърът никога не го вика директно.
Всяка заявка носи общия таен ключ ASSISTANT_TOKEN от .env.
"""
import httpx
from django.conf import settings


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
