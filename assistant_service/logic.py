"""
Какво прави асистентът: подсказка, чернова на мисия и справки.

Тук се подготвят инструкциите към модела и се проверява отговорът му,
преди да се върне на Django. Функциите се ползват от main.py (HTTP).

Трите доставчика работят заедно: заявката съдържа доставчиците по ред и
асистентът опитва следващия, ако предишният не е отговорил или е върнал
невалиден отговор.
"""
import json

from pydantic import ValidationError

import prompts
from providers import NAMES, ProviderError, ToolCall, get_provider
from schemas import (
    AnswerRequest, AnswerResponse, DraftRequest, DraftResponse, HintRequest, HintResponse, MissionDraft,
    PlanRequest, PlanResponse,
)


def first_answer(choices, action):
    """
    Вика action(доставчик) за всеки доставчик по ред и връща (резултат, име на доставчика)
    от първия успешен. Ако никой не отговори, грешката изрежда какво се е случило с всеки.
    """
    problems = []
    for choice in choices:
        try:
            provider = get_provider(choice.provider, choice.model)
            return action(provider), choice.provider
        except (ProviderError, ValueError) as error:  # ValueError – невалиден JSON
            problems.append(f"{NAMES.get(choice.provider, choice.provider)}: {error}")
    if len(problems) == 1:
        raise ProviderError(problems[0].split(": ", 1)[1])
    raise ProviderError("Нито един езиков модел не отговори. " + " ".join(problems))


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

    hint, used = first_answer(request.providers, ask)
    return HintResponse(hint=hint, provider=used)


# ---------- Ф11: чернова на мисия ----------

def draft_schema(guild_names):
    """Фиксираният JSON формат на черновата. Гилдията е ограничена до съществуващите."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "criteria": {"type": "string"},
            "guild": {"type": "string", "enum": guild_names},
            "xp": {"type": "integer"},
        },
        "required": ["title", "description", "criteria", "guild", "xp"],
        "additionalProperties": False,
    }


def make_draft(request: DraftRequest) -> DraftResponse:
    names = [guild.name for guild in request.guilds]
    guilds_text = "\n".join(f"- {g.name}" + (f": {g.description}" if g.description else "") for g in request.guilds)
    system = prompts.DRAFT.format(max_xp=request.max_xp, guilds=guilds_text)

    def ask(provider):
        raw = provider.json(system, request.idea, draft_schema(names))
        # Проверяваме отговора, преди да го покажем (раздел 3.2 на плана).
        # Ако е невалиден, се опитва следващият доставчик.
        try:
            draft = MissionDraft.model_validate(raw)
        except ValidationError:
            raise ProviderError("черновата е в неочакван формат")
        if draft.guild not in names:
            raise ProviderError("предложена е несъществуваща гилдия")
        draft.xp = max(1, min(draft.xp, request.max_xp))  # XP се ограничава от правилата на играта
        return draft

    draft, used = first_answer(request.providers, ask)
    return DraftResponse(**draft.model_dump(), provider=used)


# ---------- Справки с извикване на функции ----------

def plan_query(request: PlanRequest) -> PlanResponse:
    context = request.context
    system = prompts.QUERY_PLAN.format(today=context.today or "неизвестно",
                                       now_period=context.now_period or "няма учебен час")
    allowed = {tool.name for tool in request.tools}

    def ask(provider):
        result = provider.choose_tool(system, request.question, request.tools)
        if isinstance(result, ToolCall) and result.name not in allowed:
            raise ProviderError("избрана е справка, която не е разрешена")
        return result

    result, used = first_answer(request.providers, ask)
    if isinstance(result, ToolCall):
        return PlanResponse(tool=result.name, arguments=result.arguments, provider=used)
    return PlanResponse(answer=result or "Не разбрах въпроса. Опитайте да го зададете по друг начин.",
                        provider=used)


def answer_query(request: AnswerRequest) -> AnswerResponse:
    user = (f"Въпрос: {request.question}\n\nСправка: {request.tool}\n\n"
            f"Данни:\n{json.dumps(request.data, ensure_ascii=False, indent=1)}")

    def ask(provider):
        answer = provider.text(prompts.QUERY_ANSWER, user)
        if not answer:
            raise ProviderError("празен отговор")
        return answer

    answer, used = first_answer(request.providers, ask)
    return AnswerResponse(answer=answer, provider=used)
