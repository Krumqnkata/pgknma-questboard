"""Смяна на паролата – задължителна след първия вход с временна парола."""
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy


class QuestboardPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)  # сменя паролата и запазва входа
        user = self.request.user
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        messages.success(self.request, "Паролата е сменена.")
        return response
