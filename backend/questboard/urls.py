"""Главните адреси на сайта."""
from django.contrib import admin
from django.urls import include, path

from accounts.forms import AdminLoginForm

admin.site.site_header = "Questboard – администрация"
admin.site.site_title = "Questboard"
admin.site.index_title = "Управление на платформата"
admin.site.login_form = AdminLoginForm  # спира входа след много грешни пароли

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("web.urls")),
]
