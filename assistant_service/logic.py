"""
Какво прави асистентът: подсказка, чернова на мисия и справки.

Тук се подготвят инструкциите към модела и се проверява отговорът му,
преди да се върне на Django. Функциите се ползват и от main.py (HTTP),
и от evaluation/evaluate.py (контролните случаи).
"""
import json

from pydantic import ValidationError

import prompts
from providers import ProviderError, ToolCall, get_provider
from schemas import (
    AnswerRequest, DraftRequest, HintRequest, MissionDraft, PlanRequest, PlanResponse,
)


def make_hint(request: HintRequest) -> str:
    mission = request.mission
    user = (f"Мисия: {mission.title}\n\nОписание: {mission.description}\n\n"
            f"Критерий за изпълнение: {mission.criteria}")
    hint = get_provider(request.provider, request.model).text(prompts.HINT, user)
    if not hint:
        raise ProviderError("Асистентът върна празен отговор.")
    return hint


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


def make_draft(request: DraftRequest) -> MissionDraft:
    names = [guild.name for guild in request.guilds]
    guilds_text = "\n".join(f"- {g.name}" + (f": {g.description}" if g.description else "") for g in request.guilds)
    system = prompts.DRAFT.format(max_xp=request.max_xp, guilds=guilds_text)

    raw = get_provider(request.provider, request.model).json(system, request.idea, draft_schema(names))

    # Проверяваме отговора, преди да го покажем (раздел 3.2 на плана).
    try:
        draft = MissionDraft.model_validate(raw)
    except ValidationError:
        raise ProviderError("Асистентът върна чернова в неочакван формат. Опитайте отново.")
    if draft.guild not in names:
        raise ProviderError("Асистентът предложи несъществуваща гилдия. Опитайте отново.")
    # XP се ограничава от правилата на играта.
    draft.xp = max(1, min(draft.xp, request.max_xp))
    return draft


def plan_query(request: PlanRequest) -> PlanResponse:
    context = request.context
    system = prompts.QUERY_PLAN.format(today=context.today or "неизвестно",
                                       now_period=context.now_period or "няма учебен час")
    result = get_provider(request.provider, request.model).choose_tool(system, request.question, request.tools)

    allowed = {tool.name for tool in request.tools}
    if isinstance(result, ToolCall):
        if result.name not in allowed:
            raise ProviderError("Асистентът избра справка, която не е разрешена.")
        return PlanResponse(tool=result.name, arguments=result.arguments)
    return PlanResponse(answer=result or "Не разбрах въпроса. Опитайте да го зададете по друг начин.")


def answer_query(request: AnswerRequest) -> str:
    user = (f"Въпрос: {request.question}\n\nСправка: {request.tool}\n\n"
            f"Данни:\n{json.dumps(request.data, ensure_ascii=False, indent=1)}")
    answer = get_provider(request.provider, request.model).text(prompts.QUERY_ANSWER, user)
    if not answer:
        raise ProviderError("Асистентът върна празен отговор.")
    return answer
