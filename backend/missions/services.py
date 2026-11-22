"""
Правилата около мисиите и заявките.

Страниците и API-то викат тези функции, вместо сами да пишат в базата.
Така едно правило е написано само веднъж и се тества на едно място.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .errors import GameRuleError  # noqa: F401 – другите модули я внасят оттук
from .models import Claim, EvidenceFile, Mission

EVIDENCE_MAX_LENGTH = 2000


def missions_for_student():
    """Мисиите, които ученикът вижда: активни и с неизтекъл срок."""
    return Mission.objects.filter(is_active=True, deadline__gte=timezone.now()).select_related("guild")


def missions_for_teacher(teacher):
    """Мисиите, които учителят е създал."""
    return Mission.objects.filter(created_by=teacher).select_related("guild")


def submit_claim(student, mission, evidence, files=()):
    """
    Ученикът заявява, че е изпълнил мисия (Ф4). Доказателството е текст
    (описание или връзка) и/или до няколко снимки или PDF файла.

    Граничните случаи от раздел 3.1 на плана:
      - втора заявка за същата мисия → грешка;
      - заявка след крайния срок → грешка;
      - отказана заявка може да се подаде отново (новите файлове заменят старите).
    """
    from economy.models import GameSettings  # тук, за да няма кръгов import

    from .evidence import prepare_all

    if not student.is_student:
        raise GameRuleError("Само ученици могат да заявяват изпълнение на мисия.")

    evidence = (evidence or "").strip()
    if len(evidence) > EVIDENCE_MAX_LENGTH:
        raise GameRuleError(f"Доказателството е най-много {EVIDENCE_MAX_LENGTH} символа.")
    # Файловете се проверяват преди всичко останало – нищо не се записва, ако някой е невалиден.
    prepared = prepare_all(files, GameSettings.load())
    if not evidence and not prepared:
        raise GameRuleError("Добавете доказателство: кратък текст, връзка или файл.")

    if not mission.is_open():
        raise GameRuleError("Мисията вече не приема заявки: срокът е изтекъл или е спряна.")

    with transaction.atomic():
        # select_for_update заключва реда, докато трае транзакцията,
        # за да не минат две едновременни заявки (двойно натискане).
        claim = Claim.objects.select_for_update().filter(mission=mission, student=student).first()

        if claim is None:
            try:
                with transaction.atomic():
                    claim = Claim.objects.create(mission=mission, student=student, evidence=evidence)
            except IntegrityError:
                # Другата заявка е била записана между проверката и create().
                # Базата я спира с ограничението one_claim_per_student_per_mission.
                raise GameRuleError("Вече имате заявка за тази мисия.")
            _attach(claim, prepared)
            return claim

        if claim.status == Claim.Status.REJECTED:
            claim.evidence = evidence
            claim.status = Claim.Status.PENDING
            claim.submitted_at = timezone.now()
            claim.reviewed_by = None
            claim.reviewed_at = None
            claim.review_comment = ""
            claim.save()
            if prepared:
                claim.files.all().delete()  # новите файлове заменят старите (сигналът трие и самите файлове)
            _attach(claim, prepared)
            return claim

    raise GameRuleError("Вече имате заявка за тази мисия.")


def _attach(claim, prepared):
    for item in prepared:
        record = EvidenceFile(claim=claim, kind=item.kind, original_name=item.original_name, size=item.content.size)
        record.file.save("evidence", item.content, save=False)  # името се сменя на случайно (evidence_path)
        record.save()
