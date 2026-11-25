"""
Какво прави асистентът: подсказка, чернова на мисия и справки.

Тук се подготвят инструкциите към модела и се проверява отговорът му,
преди да се върне на Django. Функциите се ползват от main.py (HTTP).

Всяка заявка казва кой доставчик и модел да се ползва (избират се в Django admin).
Ако моделът не отговори или върне невалиден отговор, грешката се връща на Django
с ясно съобщение – резервни доставчици няма.
"""
import json
import time

from pydantic import ValidationError

import prompts
from providers import ProviderError, ToolCall, get_provider
from schemas import (
    AnswerRequest, AnswerResponse, CheckRequest, CheckResponse, DiagnoseRequest, DraftRequest, DraftResponse,
    HintRequest, HintResponse, MissionDraft, PlanRequest, PlanResponse, QuizDraftRequest, QuizDraftResponse,
    QuizQuestion,
)


def answer_with(choice, action):
    """
    Вика action(модел) с избрания доставчик и връща (резултат, име на доставчика).
    Грешките на модела стигат до Django като ProviderError с ясно съобщение.
    """
    provider = get_provider(choice.provider, choice.model)
    try:
        return action(provider), choice.provider
    except ValueError:  # моделът е върнал невалиден JSON
        raise ProviderError("Моделът върна отговор в неочакван формат. Опитайте отново.")


# ---------- Проверка от администрацията ----------

def check_model(request: CheckRequest) -> CheckResponse:
    """Една кратка заявка към избрания модел – за бутона „Провери асистента“ в admin."""
    started = time.monotonic()
    try:
        answer, used = answer_with(request, lambda provider: provider.text(prompts.CHECK, "Готов ли си?"))
    except ProviderError as error:
        return CheckResponse(ok=False, provider=request.provider, model=request.model,
                             seconds=round(time.monotonic() - started, 1), error=str(error), detail=error.detail)
    return CheckResponse(ok=bool(answer), provider=used, model=request.model,
                         seconds=round(time.monotonic() - started, 1), answer=answer[:200],
                         error="" if answer else "Моделът върна празен отговор.")


def plain(text):
    """Дългите тирета стават къси: така пишем навсякъде в сайта."""
    return text.replace("—", "-")


# ---------- Ф10: подсказка ----------

def make_hint(request: HintRequest) -> HintResponse:
    mission = request.mission
    user = (f"Мисия: {mission.title}\n\nОписание: {mission.description}\n\n"
            f"Критерий за изпълнение: {mission.criteria}")

    def ask(provider):
        hint = provider.text(prompts.HINT, user)
        if not hint:
            raise ProviderError("празен отговор")
        return hint

    hint, used = answer_with(request, ask)
    return HintResponse(hint=plain(hint), provider=used)


# ---------- Ф11: чернова на мисия ----------

NO_BADGE = "без значка"  # празен текст не се приема като възможна стойност от всички модели


def draft_schema(guild_names, badge_names):
    """Фиксираният JSON формат на черновата. Гилдията и значката са ограничени до съществуващите."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "criteria": {"type": "string"},
            "guild": {"type": "string", "enum": guild_names},
            "xp": {"type": "integer"},
            "is_group": {"type": "boolean"},
            "team_min": {"type": "integer"},
            "team_max": {"type": "integer"},
            "badge": {"type": "string", "enum": [NO_BADGE, *badge_names]},
        },
        "required": ["title", "description", "criteria", "guild", "xp", "is_group", "team_min", "team_max", "badge"],
        "additionalProperties": False,
    }


def make_draft(request: DraftRequest) -> DraftResponse:
    names = [guild.name for guild in request.guilds]
    guilds_text = "\n".join(f"- {g.name}" + (f": {g.description}" if g.description else "") for g in request.guilds)
    badge_names = [badge.name for badge in request.badges]
    badges_text = "\n".join(f"- {b.name}: {b.description}" for b in request.badges) or "- няма"
    system = prompts.DRAFT.format(max_xp=request.max_xp, guilds=guilds_text, badges=badges_text,
                                  team_limit=request.team_limit)

    def ask(provider):
        raw = provider.json(system, request.idea, draft_schema(names, badge_names))
        # Проверяваме отговора, преди да го покажем (раздел 3.2 на плана).
        # Ако е невалиден, потребителят получава ясна грешка вместо съмнителна чернова.
        try:
            draft = MissionDraft.model_validate(raw)
        except ValidationError:
            raise ProviderError("черновата е в неочакван формат")
        if draft.guild not in names:
            raise ProviderError("предложена е несъществуваща гилдия")
        # Само текстовете; имената на гилдията и значката остават точно каквито са.
        draft.title, draft.description, draft.criteria = plain(draft.title), plain(draft.description), plain(draft.criteria)
        draft.xp = max(1, min(draft.xp, request.max_xp))  # XP се ограничава от правилата на играта
        draft.team_min = max(2, min(draft.team_min, request.team_limit))
        draft.team_max = max(draft.team_min, min(draft.team_max, request.team_limit))
        if draft.badge not in badge_names:
            draft.badge = ""
        return draft

    draft, used = answer_with(request, ask)
    return DraftResponse(**draft.model_dump(), provider=used)


# ---------- Справки с извикване на функции ----------

def with_history(request, text):
    """Въпросът заедно с последните реплики – за „а в четвъртък?“."""
    if not request.history:
        return text
    names = {"user": "Потребител", "assistant": "Асистент"}
    lines = "\n".join(f"{names[item.role]}: {item.text}" for item in request.history)
    return f"Разговорът досега (само за контекст):\n{lines}\n\n{text}"


def plan_query(request: PlanRequest) -> PlanResponse:
    context = request.context
    system = prompts.QUERY_PLAN.format(today=context.today or "неизвестно", now=context.now or "неизвестно",
                                       role=context.role or "неизвестна",
                                       now_period=context.now_period or "няма учебен час")
    allowed = {tool.name for tool in request.tools}

    def ask(provider):
        result = provider.choose_tool(system, with_history(request, f"Въпрос: {request.question}"), request.tools)
        if isinstance(result, ToolCall) and result.name not in allowed:
            raise ProviderError("избрана е справка, която не е разрешена")
        return result

    result, used = answer_with(request, ask)
    if isinstance(result, ToolCall):
        return PlanResponse(tool=result.name, arguments=result.arguments, provider=used)
    return PlanResponse(answer=plain(result) or "Не разбрах въпроса. Опитайте да го зададете по друг начин.",
                        provider=used)


def answer_query(request: AnswerRequest) -> AnswerResponse:
    user = (f"Въпрос: {request.question}\n\nСправка: {request.tool}\n\n"
            f"Данни:\n{json.dumps(request.data, ensure_ascii=False, indent=1)}")

    def ask(provider):
        answer = provider.text(prompts.QUERY_ANSWER, with_history(request, user))
        if not answer:
            raise ProviderError("празен отговор")
        return answer

    answer, used = answer_with(request, ask)
    return AnswerResponse(answer=plain(answer), provider=used)


# ---------- Проверка на системата ----------

def explain_problems(request: DiagnoseRequest) -> AnswerResponse:
    lines = [f"- {item.title}: {item.count}. {item.advice} "
             + (f"Има бутон „{item.fix}“." if item.fix else "Поправя се ръчно.") for item in request.problems]

    def ask(provider):
        answer = provider.text(prompts.DIAGNOSE, "Намерени проблеми:\n" + "\n".join(lines))
        if not answer:
            raise ProviderError("празен отговор")
        return answer

    answer, used = answer_with(request, ask)
    return AnswerResponse(answer=plain(answer), provider=used)


# ---------- Въпроси за тест ----------

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "correct": {"type": "integer"},
        },
        "required": ["text", "options", "correct"],
        "additionalProperties": False,
    }}},
    "required": ["questions"],
    "additionalProperties": False,
}


def make_quiz(request: QuizDraftRequest) -> QuizDraftResponse:
    system = prompts.QUIZ.format(count=request.count, guild=request.guild, about=request.guild_description or "няма",
                                 seconds=request.seconds)

    def ask(provider):
        raw = provider.json(system, request.topic, QUIZ_SCHEMA)
        good = []
        for item in raw.get("questions", []):
            try:
                question = QuizQuestion.model_validate(item)
            except ValidationError:
                continue
            if len({option.strip().casefold() for option in question.options}) == 4:  # еднакви отговори не се приемат
                good.append(question)
        if not good:
            raise ProviderError("моделът не предложи годни въпроси")
        return good[:request.count]

    questions, used = answer_with(request, ask)
    return QuizDraftResponse(questions=questions, provider=used)
