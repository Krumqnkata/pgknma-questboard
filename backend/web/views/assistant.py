"""
Страници, които ползват асистента: подсказка по мисия, чернова на мисия
и чатът за справки. Ако асистентът не работи, се показва ясно съобщение,
а останалата част от платформата продължава да работи.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from assistant_bridge.services import AssistantError, request_hint
from missions.models import Mission
from missions.services import GameRuleError

STUDENT = User.Role.STUDENT
TEACHER = User.Role.TEACHER


@require_POST
@role_required(STUDENT)
def mission_hint(request, pk):
    """Ученикът харчи Hint Token за подсказка по мисия (Ф10)."""
    mission = get_object_or_404(Mission, pk=pk, is_active=True)
    try:
        request_hint(request.user, mission)
    except (GameRuleError, AssistantError) as error:
        messages.error(request, f"{error} Hint Token-ът не е похарчен." if isinstance(error, AssistantError)
                       else str(error))
    else:
        messages.success(request, "Подсказката е готова. Похарчен е 1 Hint Token.")
    return redirect("mission_detail", pk=mission.pk)


@role_required(STUDENT, TEACHER)
def assistant_chat(request):
    """Чат със асистента за справки. Самият разговор става с JavaScript през REST API-то."""
    return render(request, "web/assistant.html")
