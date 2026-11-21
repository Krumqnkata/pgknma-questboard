"""
Услуга на асистента (FastAPI).

Отделна програма от основното API. Тя:
  - пази ключа за езиковия модел (Django не го знае);
  - приема заявки само от Django, с общия таен ключ ASSISTANT_TOKEN;
  - не чете базата данни – получава от Django само нужните данни, без лични данни.

Стартиране (от тази папка):  python -m uvicorn main:app --port 8001
"""
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status

import config

app = FastAPI(
    title="Questboard – асистент",
    description="Подсказки, чернови на мисии и справки по разписанието.",
    version="0.1.0",
)


def require_token(x_assistant_token: str = Header(default="")):
    """Пуска заявката само ако носи правилния таен ключ от Django."""
    if not config.ASSISTANT_TOKEN:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ASSISTANT_TOKEN не е настроен в .env")
    # compare_digest сравнява за едно и също време – не издава колко символа съвпадат
    if not secrets.compare_digest(x_assistant_token, config.ASSISTANT_TOKEN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невалиден ключ")


@app.get("/health", dependencies=[Depends(require_token)])
def health():
    """Django пита тук дали асистентът работи (индикаторът в admin)."""
    return {"status": "ok"}
