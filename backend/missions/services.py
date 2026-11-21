"""
Правилата около мисиите и заявките.

Страниците и API-то викат тези функции, вместо сами да пишат в базата.
Така едно правило е написано само веднъж и се тества на едно място.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Claim, Mission

EVIDENCE_MAX_LENGTH = 2000


class GameRuleError(Exception):
    """Нарушено правило на играта. Текстът се показва на потребителя."""


def missions_for_student():
    """Мисиите, които ученикът вижда: активни и с неизтекъл срок."""
    return Mission.objects.filter(is_active=True, deadline__gte=timezone.now()).select_related("guild")


def missions_for_teacher(teacher):
    """Мисиите, които учителят е създал."""
    return Mission.objects.filter(created_by=teacher).select_related("guild")


def submit_claim(student, mission, evidence):
    """
    Ученикът заявява, че е изпълнил мисия (Ф4).

    Граничните случаи от раздел 3.1 на плана:
      - втора заявка за същата мисия → грешка;
      - заявка след крайния срок → грешка;
      - отказана заявка може да се подаде отново.
    """
    if not student.is_student:
        raise GameRuleError("Само ученици могат да заявяват изпълнение на мисия.")

    evidence = (evidence or "").strip()
    if not evidence:
        raise GameRuleError("Добавете доказателство: кратък текст или връзка.")
    if len(evidence) > EVIDENCE_MAX_LENGTH:
        raise GameRuleError(f"Доказателството е най-много {EVIDENCE_MAX_LENGTH} символа.")

    if not mission.is_open():
        raise GameRuleError("Мисията вече не приема заявки: срокът е изтекъл или е спряна.")

    with transaction.atomic():
        # select_for_update заключва реда, докато трае транзакцията,
        # за да не минат две едновременни заявки (двойно натискане).
        claim = Claim.objects.select_for_update().filter(mission=mission, student=student).first()

        if claim is None:
            try:
                with transaction.atomic():
                    return Claim.objects.create(mission=mission, student=student, evidence=evidence)
            except IntegrityError:
                # Другата заявка е била записана между проверката и create().
                # Базата я спира с ограничението one_claim_per_student_per_mission.
                raise GameRuleError("Вече имате заявка за тази мисия.")

        if claim.status == Claim.Status.REJECTED:
            claim.evidence = evidence
            claim.status = Claim.Status.PENDING
            claim.submitted_at = timezone.now()
            claim.reviewed_by = None
            claim.reviewed_at = None
            claim.review_comment = ""
            claim.save()
            return claim

    raise GameRuleError("Вече имате заявка за тази мисия.")
