"""Записва неуспешните входове и ги забравя след успешен вход."""
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from . import lockout


@receiver(user_login_failed)
def remember_failed_login(sender, credentials, request=None, **kwargs):
    lockout.record_failure(credentials.get("username") or credentials.get("email"), lockout.client_ip(request))


@receiver(user_logged_in)
def forget_failed_logins(sender, request, user, **kwargs):
    lockout.clear(user.email)
