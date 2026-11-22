"""Страницата с известията на ученика (Ф15)."""
from django.shortcuts import render

from accounts.models import User
from accounts.permissions import role_required
from notifications.services import mark_all_read, recent_for


@role_required(User.Role.STUDENT)
def notifications(request):
    items = recent_for(request.user)  # зареждат се, докато още се знае кои са нови
    mark_all_read(request.user)       # отварянето на страницата ги прави прочетени
    return render(request, "web/notifications.html", {"notifications": items})
