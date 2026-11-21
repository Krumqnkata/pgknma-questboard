"""
Проверки на ролите. Ползват се и от страниците, и от REST API-то,
за да са правилата за достъп на едно място и винаги на сървъра.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def role_required(*roles):
    """
    Декоратор за страници: пуска само влезли потребители с някоя от ролите.
    Пример: @role_required(User.Role.TEACHER)
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied  # страница 403
            return view(request, *args, **kwargs)

        return login_required(wrapper)

    return decorator


class IsStudent(BasePermission):
    """За API: само ученици."""

    message = "Това действие е само за ученици."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_student


class IsTeacher(BasePermission):
    """За API: само учители."""

    message = "Това действие е само за учители."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_teacher
