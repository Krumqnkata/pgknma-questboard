"""Вход с имейл и парола, който отказва, докато входът е спрян заради много грешки."""
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from . import lockout


class LockoutModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get("email")
        if lockout.minutes_left(email, lockout.client_ip(request)):
            # Паролата дори не се проверява. PermissionDenied спира и другите начини за вход.
            raise PermissionDenied
        return super().authenticate(request, username=username, password=password, **kwargs)
