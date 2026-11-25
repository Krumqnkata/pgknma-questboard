"""
Правилата около мисиите и заявките.

Страниците и API-то викат тези функции, вместо сами да пишат в базата.
Така едно правило е написано само веднъж и се тества на едно място.
"""
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .errors import GameRuleError  # noqa: F401 – другите модули я внасят оттук
from .models import Claim, DeadlineExtension, EvidenceFile, Mission, MissionFile

EVIDENCE_MAX_LENGTH = 2000


def visible_to(student):
    """Мисиите за всички и домашните за класа на ученика (без ученик – само мисиите)."""
    if student is None:
        return Q(kind=Mission.Kind.MISSION)
    return Q(kind=Mission.Kind.MISSION) | Q(
        pk__in=Mission.school_classes.through.objects.filter(schoolclass_id=student.school_class_id).values("mission_id"))


def missions_for_student(student=None):
    """Каквото ученикът вижда: активни, с неизтекъл срок, а от домашните – само за неговия клас."""
    now = timezone.now()
    in_time = Q(deadline__gte=now)
    if student is not None:  # и тези, чийто срок този ученик си е удължил
        in_time |= Q(pk__in=DeadlineExtension.objects.filter(student=student, until__gte=now).values("mission_id"))
    return Mission.objects.filter(visible_to(student), in_time, is_active=True).select_related("guild")


def missions_for_teacher(teacher):
    """Мисиите, които учителят е създал."""
    return Mission.objects.filter(created_by=teacher).select_related("guild")


def missions_reviewed_by(teacher):
    """Мисиите, по които учителят проверява заявки: своите и тези, на които е заместник."""
    # Подзаявка вместо JOIN, за да не се повтарят редовете и да не се объркат броенията.
    deputy = Mission.reviewers.through.objects.filter(user_id=teacher.pk).values("mission_id")
    return Mission.objects.filter(Q(created_by=teacher) | Q(pk__in=deputy)).select_related("guild")


def claims_to_decide():
    """Заявките, които чакат решение. Съотборниците се решават заедно с капитана си."""
    return Claim.objects.filter(status=Claim.Status.PENDING, captain__isnull=True)


def parse_nicknames(text):
    """„Комета, Вихър“ → ["Комета", "Вихър"] (без повторения, в същия ред)."""
    names = [name.strip() for name in (text or "").replace("\n", ",").replace(";", ",").split(",")]
    return list(dict.fromkeys(name for name in names if name))


def _find_teammates(student, mission, nicknames):
    """Учениците с тези псевдоними. Хвърля GameRuleError, ако отборът не отговаря на правилата."""
    from accounts.models import User

    nicknames = list(dict.fromkeys(nicknames))
    if not mission.is_group:
        if nicknames:
            raise GameRuleError("Мисията не е отборна.")
        return []
    if student.nickname in nicknames:
        raise GameRuleError("Ти си капитанът – не се изписвай като съотборник.")
    size = len(nicknames) + 1
    if not mission.team_min <= size <= mission.team_max:
        raise GameRuleError(f"Отборът е от {mission.team_min} до {mission.team_max} ученици заедно с теб.")
    found = {user.nickname: user for user in User.objects.filter(
        role=User.Role.STUDENT, is_active=True, nickname__in=nicknames)}
    missing = [name for name in nicknames if name not in found]
    if missing:
        raise GameRuleError("Няма ученик с псевдоним: " + ", ".join(missing) + ".")
    strangers = [user.nickname for user in found.values() if not mission.is_visible_to(user)]
    if strangers:
        raise GameRuleError("Домашната не е за класа на: " + ", ".join(strangers) + ".")
    return [found[name] for name in nicknames]


def _set_team(claim, teammates):
    """Свързва заявките на съотборниците с тази на капитана. Вика се в транзакция."""
    from notifications.models import Notification
    from notifications.services import notify

    mission = claim.mission
    # Предишният отбор (при повторно подаване) се освобождава.
    claim.team.update(captain=None)
    for mate in teammates:
        own = Claim.objects.select_for_update().filter(mission=mission, student=mate).first()
        if own is not None and own.status != Claim.Status.REJECTED:
            raise GameRuleError(f"{mate.nickname} вече има заявка или отбор за тази мисия.")
        if own is None:
            try:
                with transaction.atomic():
                    Claim.objects.create(mission=mission, student=mate, evidence="", captain=claim)
            except IntegrityError:  # друг капитан го е записал в същия момент
                raise GameRuleError(f"{mate.nickname} вече има заявка или отбор за тази мисия.")
        else:
            own.team.update(captain=None)  # ако преди е бил капитан на друг отбор
            own.files.all().delete()
            _reopen(own, evidence="", captain=claim)
        notify(mate, Notification.Kind.TEAM,
               f"{claim.student.nickname} те записа в отбора си за „{mission.title}“. "
               "Ако не участваш, напусни отбора от страницата на мисията.",
               link=reverse("mission_detail", args=[mission.pk]))


def _reopen(claim, evidence, captain=None):
    claim.evidence = evidence
    claim.captain = captain
    claim.status = Claim.Status.PENDING
    claim.submitted_at = timezone.now()
    claim.reviewed_by = None
    claim.reviewed_at = None
    claim.review_comment = ""
    claim.save()


def leave_team(student, mission):
    """Съотборник, записан по погрешка, се отказва, преди учителят да е решил."""
    from notifications.models import Notification
    from notifications.services import notify

    with transaction.atomic():
        claim = (Claim.objects.select_for_update().select_related("captain__student")
                 .filter(mission=mission, student=student, captain__isnull=False).first())
        if claim is None or claim.status != Claim.Status.PENDING:
            raise GameRuleError("Можеш да напуснеш отбора само докато заявката чака проверка.")
        captain = claim.captain.student
        if claim.xp_transactions.exists():  # журналът сочи към заявката, затова тя остава
            claim.captain, claim.status = None, Claim.Status.REJECTED
            claim.review_comment = "Ти напусна отбора."
            claim.save()
        else:
            claim.delete()
        notify(captain, Notification.Kind.TEAM, f"{student.nickname} напусна отбора ти за „{mission.title}“.",
               link=reverse("mission_detail", args=[mission.pk]))


def submit_claim(student, mission, evidence, files=(), teammates=()):
    """
    Ученикът заявява, че е изпълнил мисия (Ф4). Доказателството е текст
    (описание или връзка) и/или до няколко снимки или PDF файла.

    Граничните случаи от раздел 3.1 на плана:
      - втора заявка за същата мисия → грешка;
      - заявка след крайния срок → грешка;
      - отказана заявка може да се подаде отново (новите файлове заменят старите);
      - срокът може да е по-късен само за този ученик (missions/deadlines.py).

    При отборна мисия teammates са псевдонимите на съотборниците; подалият е капитанът.
    """
    from economy.models import GameSettings  # тук, за да няма кръгов import

    from .deadlines import can_submit
    from .evidence import prepare_all

    if not student.is_student:
        raise GameRuleError("Само ученици могат да заявяват изпълнение на мисия.")

    if not mission.is_visible_to(student):
        raise GameRuleError("Тази домашна не е за твоя клас.")

    evidence = (evidence or "").strip()
    if len(evidence) > EVIDENCE_MAX_LENGTH:
        raise GameRuleError(f"Доказателството е най-много {EVIDENCE_MAX_LENGTH} символа.")
    # Файловете се проверяват преди всичко останало – нищо не се записва, ако някой е невалиден.
    prepared = prepare_all(files, GameSettings.load())
    if not evidence and not prepared:
        raise GameRuleError("Добавете доказателство: кратък текст, връзка или файл.")

    if not can_submit(student, mission):
        raise GameRuleError("Мисията вече не приема заявки: срокът е изтекъл или е спряна.")

    mates = _find_teammates(student, mission, teammates)

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
            _set_team(claim, mates)
            _attach(claim, prepared)
            return claim

        if claim.status == Claim.Status.REJECTED:
            _reopen(claim, evidence)
            _set_team(claim, mates)
            if prepared:
                claim.files.all().delete()  # новите файлове заменят старите (сигналът трие и самите файлове)
            _attach(claim, prepared)
            return claim

    if claim.captain_id:
        raise GameRuleError(f"Вече си в отбора на {claim.captain.student.nickname}.")
    raise GameRuleError("Вече имате заявка за тази мисия.")


def _attach(claim, prepared):
    for item in prepared:
        record = EvidenceFile(claim=claim, kind=item.kind, original_name=item.original_name, size=item.content.size)
        record.file.save("evidence", item.content, save=False)  # името се сменя на случайно (evidence_path)
        record.save()


def attach_to_mission(mission, prepared):
    """Файловете на учителя към мисията (указания, образец, плакат)."""
    for item in prepared:
        record = MissionFile(mission=mission, kind=item.kind, original_name=item.original_name, size=item.content.size)
        record.file.save("mission", item.content, save=False)
        record.save()
