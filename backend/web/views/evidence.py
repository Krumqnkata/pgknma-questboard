"""
Показва снимка или PDF към доказателство – само на ученика, на учителя,
създал мисията, и на администратора. За всички останали файлът „не съществува“ (404).
"""
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from missions.models import EvidenceFile


def can_see(user, claim):
    return user.is_admin_role or user.pk in (claim.student_id, claim.mission.created_by_id)


@login_required
def evidence_file(request, pk):
    record = get_object_or_404(EvidenceFile.objects.select_related("claim", "claim__mission"), pk=pk)
    if not can_see(request.user, record.claim):
        raise Http404("Няма такъв файл.")
    try:
        file = record.file.open("rb")
    except FileNotFoundError:
        raise Http404("Файлът липсва.")
    content_type = "application/pdf" if record.kind == EvidenceFile.Kind.PDF else "image/jpeg"
    response = FileResponse(file, content_type=content_type, filename=record.original_name)
    # Файлът се показва, но не може да изпълнява скриптове, и не се пази в споделен кеш.
    response["Content-Security-Policy"] = "sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=3600"
    return response
