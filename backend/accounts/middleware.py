"""
Потребител с временна парола (внесен от CSV) не може да прави нищо друго,
докато не си смени паролата. Така временната парола, раздадена на лист,
спира да важи веднага след първия вход.
"""
from django.shortcuts import redirect
from django.urls import reverse

# Адреси, които са позволени и с временна парола
ALLOWED_PATHS = ("password_change", "logout", "terms", "privacy", "manifest", "service_worker", "offline",
                 "favicon")


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            allowed = {reverse(name) for name in ALLOWED_PATHS}
            if request.path not in allowed and not request.path.startswith(("/static/", "/school-logo/")):
                return redirect("password_change")
        return self.get_response(request)
