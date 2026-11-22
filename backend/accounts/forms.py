"""Формите за вход – на сайта и в администрацията."""
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from . import lockout


class LockoutMixin:
    """Ако входът е спрян, казва колко минути да се изчака, вместо „грешна парола“."""

    locked_minutes = 0

    def clean(self):
        email, ip = self.data.get("username"), lockout.client_ip(self.request)
        self.check_lock(email, ip)
        try:
            return super().clean()
        except ValidationError:
            self.check_lock(email, ip)  # този опит може да е бил последният позволен
            raise

    def check_lock(self, email, ip):
        self.locked_minutes = lockout.minutes_left(email, ip)
        if self.locked_minutes:
            raise ValidationError(
                "Твърде много неуспешни опити за вход. Опитайте отново след %(minutes)s мин.",
                code="locked", params={"minutes": self.locked_minutes},
            )


class LoginForm(LockoutMixin, AuthenticationForm):
    pass


class AdminLoginForm(LockoutMixin, AdminAuthenticationForm):
    pass
