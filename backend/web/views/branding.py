"""Логото на училището. Качва се от администрацията и се пази извън кода."""
import mimetypes

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_control

from economy.models import GameSettings, Sponsor


@cache_control(public=True, max_age=86400)
def school_logo(request):
    """
    Връща само логото – не всички качени файлове. Така никой не може да
    отвори друг файл от сървъра, като промени адреса.
    """
    logo = GameSettings.load().school_logo
    if not logo:
        raise Http404("Няма качено лого.")
    return _send_logo(logo)


@cache_control(public=True, max_age=86400)
def sponsor_logo(request, name):
    """Логото на спонсор. Името на файла трябва да е записано при някой спонсор."""
    return _send_logo(get_object_or_404(Sponsor, logo=f"sponsors/{name}").logo)


def _send_logo(logo):
    try:
        file = logo.open("rb")
    except FileNotFoundError:
        raise Http404("Файлът на логото липсва.")
    content_type = mimetypes.guess_type(logo.name)[0] or "application/octet-stream"
    return FileResponse(file, content_type=content_type)
