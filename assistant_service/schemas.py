"""
Форматите на заявките и отговорите на асистента (Pydantic).

FastAPI проверява всяка заявка по тях и връща грешка 422, ако нещо липсва.
Отговорите на езиковия модел също минават през тези модели, преди да се върнат.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["openai", "gemini", "claude", "fake"]


class ProviderChoice(BaseModel):
    provider: Provider
    model: str = ""


class ModelChoice(BaseModel):
    """
    Доставчиците по ред – избират се в Django admin. Асистентът опитва първия,
    а ако той не отговори (няма ключ, грешка, забавяне) – следващия.
    """

    providers: list[ProviderChoice] = Field(min_length=1, max_length=3)


class Answered(BaseModel):
    """Всеки отговор казва кой модел е отговорил – записва се в журнала."""

    provider: str = ""


# ---------- Подсказка (Ф10) ----------

class MissionText(BaseModel):
    title: str = Field(max_length=200)
    description: str = Field(max_length=4000)
    criteria: str = Field(max_length=2000)


class HintRequest(ModelChoice):
    mission: MissionText


class HintResponse(Answered):
    hint: str


# ---------- Чернова на мисия (Ф11) ----------

class GuildInfo(BaseModel):
    name: str
    description: str = ""


class DraftRequest(ModelChoice):
    idea: str = Field(min_length=5, max_length=1000)
    guilds: list[GuildInfo] = Field(min_length=1)
    max_xp: int = Field(ge=1)


class MissionDraft(BaseModel):
    """Черновата, която моделът трябва да върне (фиксиран JSON формат)."""

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    criteria: str = Field(min_length=5, max_length=2000)
    guild: str
    xp: int


class DraftResponse(MissionDraft, Answered):
    pass


# ---------- Справки с извикване на функции (Ф17, Ф18, Ф22, Ф14) ----------

class ToolDefinition(BaseModel):
    """Справка, която моделът може да избере. Описва се от Django, не от асистента."""

    name: str
    description: str
    parameters: dict[str, Any]


class QueryContext(BaseModel):
    today: str = ""          # напр. „вторник“
    now_period: str = ""     # текущ учебен час или празно
    role: str = ""           # ученик / учител / администратор


class PlanRequest(ModelChoice):
    question: str = Field(min_length=1, max_length=500)
    tools: list[ToolDefinition]
    context: QueryContext = QueryContext()


class PlanResponse(Answered):
    """Или избрана справка с параметри, или кратък текстов отговор без справка."""

    tool: str | None = None
    arguments: dict[str, Any] = {}
    answer: str | None = None


class AnswerRequest(ModelChoice):
    question: str = Field(min_length=1, max_length=500)
    tool: str
    data: dict[str, Any]


class AnswerResponse(Answered):
    answer: str
