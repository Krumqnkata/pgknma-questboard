"""Страница при изтекла форма (CSRF). Останалите грешки са в templates/404.html, 403.html, 500.html."""
from django.shortcuts import render


def csrf_failure(request, reason=""):
    return render(request, "403_csrf.html", status=403)
