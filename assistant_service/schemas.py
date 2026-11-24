"""
Форматите на заявките и отговорите на асистента (Pydantic).

FastAPI проверява всяка заявка по тях и връща грешка 422, ако нещо липсва.
Отговорите на езиковия модел също минават през тези модели, преди да се върнат.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["openai", "gemini", "claude", "fake"]


class ModelChoice(BaseModel):
    """Доставчикът и моделът – избират се в Django admin („Настройки на играта“)."""

    provider: Provider
    model: str = Field(min_length=1, max_length=100)


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
    badges: list[GuildInfo] = []          # значки, които се печелят само от мисия
    team_limit: int = Field(default=10, ge=2)


class MissionDraft(BaseModel):
    """Черновата, която моделът трябва да върне (фиксиран JSON формат)."""

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)
    criteria: str = Field(min_length=5, max_length=2000)
    guild: str
    xp: int
    is_group: bool = False
    team_min: int = 2
    team_max: int = 4
    badge: str = ""


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
    now: str = ""            # напр. „вторник, 24 ноември 2026 г., 14:05“
    now_period: str = ""     # текущ учебен час или празно
    role: str = ""           # ученик / учител / администратор


class ChatMessage(BaseModel):
    """Предишна реплика. Имената на учителите са заменени с кодове още в Django."""

    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class PlanRequest(ModelChoice):
    question: str = Field(min_length=1, max_length=500)
    history: list[ChatMessage] = Field(default=[], max_length=10)
    tools: list[ToolDefinition]
    context: QueryContext = QueryContext()


class PlanResponse(Answered):
    """Или избрана справка с параметри, или кратък текстов отговор без справка."""

    tool: str | None = None
    arguments: dict[str, Any] = {}
    answer: str | None = None


class AnswerRequest(ModelChoice):
    question: str = Field(min_length=1, max_length=500)
    history: list[ChatMessage] = Field(default=[], max_length=10)
    tool: str
    data: dict[str, Any]


class AnswerResponse(Answered):
    answer: str


# ---------- Проверка на системата ----------

class ProblemInfo(BaseModel):
    """Вид и брой на проблема – без имена и данни за хора."""

    title: str = Field(max_length=200)
    count: int = Field(ge=1)
    advice: str = Field(max_length=500)
    fix: str = ""  # надписът на бутона за поправка; празно – поправя се ръчно


class DiagnoseRequest(ModelChoice):
    problems: list[ProblemInfo] = Field(min_length=1, max_length=50)


# ---------- Въпроси за тест ----------

class QuizDraftRequest(ModelChoice):
    topic: str = Field(min_length=3, max_length=300)
    guild: str = Field(max_length=50)
    guild_description: str = Field(default="", max_length=300)
    count: int = Field(ge=1, le=10)
    seconds: int = Field(ge=5, le=600)


class QuizQuestion(BaseModel):
    text: str = Field(min_length=5, max_length=600)
    options: list[str] = Field(min_length=4, max_length=4)
    correct: int = Field(ge=0, le=3)


class QuizDraftResponse(Answered):
    questions: list[QuizQuestion]


# ---------- Проверка от администрацията ----------

class CheckRequest(ModelChoice):
    pass


class CheckResponse(Answered):
    """Резултатът от бутона „Провери асистента“: кратък отговор или ясна грешка."""

    ok: bool
    model: str
    seconds: float = 0
    answer: str = ""
    error: str = ""
    detail: str = ""  # оригиналното съобщение на доставчика (на английски) – за администратора
