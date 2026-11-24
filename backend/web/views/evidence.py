"""
Показва файл към доказателство – само на ученика, на отбора му, на учителите, които
проверяват мисията, и на администратора. Файловете към мисия се виждат от всеки, който
вижда самата мисия. За всички останали файлът „не съществува“ (404).
"""
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from missions.models import Claim, EvidenceFile, FileKind, MissionFile


def can_see(user, claim):
    if user.pk == claim.student_id or claim.mission.can_be_reviewed_by(user):
        return True
    return claim.team.filter(student=user).exists()  # съотборник на капитана


def can_see_mission(user, mission):
    if user.is_admin_role or user.is_teacher:
        return True
    if mission.is_active and mission.is_visible_to(user):
        return True
    return Claim.objects.filter(mission=mission, student=user).exists()


CONTENT_TYPES = {
    FileKind.IMAGE: "image/jpeg",
    FileKind.PDF: "application/pdf",
    FileKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileKind.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@login_required
def evidence_file(request, pk):
    record = get_object_or_404(EvidenceFile.objects.select_related("claim", "claim__mission"), pk=pk)
    if not can_see(request.user, record.claim):
        raise Http404("Няма такъв файл.")
    return _send(record)


@login_required
def mission_file(request, pk):
    record = get_object_or_404(MissionFile.objects.select_related("mission"), pk=pk)
    if not can_see_mission(request.user, record.mission):
        raise Http404("Няма такъв файл.")
    return _send(record)


def _send(record):
    try:
        file = record.file.open("rb")
    except FileNotFoundError:
        raise Http404("Файлът липсва.")
    # Снимките и PDF се отварят в браузъра, документите на Office само се изтеглят.
    response = FileResponse(file, content_type=CONTENT_TYPES[record.kind], filename=record.original_name,
                            as_attachment=record.kind not in (FileKind.IMAGE, FileKind.PDF))
    # Файлът се показва, но не може да изпълнява скриптове, и не се пази в споделен кеш.
    response["Content-Security-Policy"] = "sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response
