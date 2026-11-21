"""
Услуга на асистента (FastAPI).

Отделна програма от основното API. Тя:
  - пази ключовете за езиковите модели (Django не ги знае);
  - приема заявки само от Django, с общия таен ключ ASSISTANT_TOKEN;
  - не чете базата данни – получава от Django само нужните данни, без лични данни на ученици.

Стартиране (от тази папка):  python -m uvicorn main:app --port 8001
Документация на адресите:    http://127.0.0.1:8001/docs
"""
import secrets

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status

import config
import logic
from providers import ProviderError
from schemas import (
    AnswerRequest, AnswerResponse, DraftRequest, HintRequest, HintResponse, MissionDraft, PlanRequest, PlanResponse,
)

app = FastAPI(
    title="Questboard – асистент",
    description="Подсказки, чернови на мисии и справки по разписанието.",
    version="0.2.0",
)


def require_token(x_assistant_token: str = Header(default="")):
    """Пуска заявката само ако носи правилния таен ключ от Django."""
    if not config.ASSISTANT_TOKEN:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ASSISTANT_TOKEN не е настроен в .env")
    # compare_digest сравнява за едно и също време – не издава колко символа съвпадат
    if not secrets.compare_digest(x_assistant_token, config.ASSISTANT_TOKEN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невалиден ключ")


# Всички адреси по-долу изискват тайния ключ.
router = APIRouter(dependencies=[Depends(require_token)])


def run(function, request):
    """Вика логиката и превръща грешките на модела в отговор 502 с ясно съобщение."""
    try:
        return function(request)
    except ProviderError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error))
    except ValueError:  # напр. невалиден JSON от модела
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Асистентът върна неочакван отговор. Опитайте отново.")


@router.get("/health")
def health():
    """Django пита тук дали асистентът работи (индикаторът в admin)."""
    return {"status": "ok"}


# Функциите са обикновени (def), затова FastAPI ги пуска в отделни нишки
# и бавният отговор на модела не спира другите заявки.

@router.post("/hint", response_model=HintResponse)
def hint(request: HintRequest):
    """Подсказка по мисия (Ф10). Насока, а не готово решение."""
    return HintResponse(hint=run(logic.make_hint, request))


@router.post("/mission-draft", response_model=MissionDraft)
def mission_draft(request: DraftRequest):
    """Чернова на мисия по идея на учителя (Ф11). Отговорът е проверен JSON."""
    return run(logic.make_draft, request)


@router.post("/query/plan", response_model=PlanResponse)
def query_plan(request: PlanRequest):
    """Първа стъпка на справка: моделът избира коя справка да изпълни Django (извикване на функции)."""
    return run(logic.plan_query, request)


@router.post("/query/answer", response_model=AnswerResponse)
def query_answer(request: AnswerRequest):
    """Втора стъпка: моделът оформя отговора само от данните, които Django е върнал."""
    return AnswerResponse(answer=run(logic.answer_query, request))


app.include_router(router)
