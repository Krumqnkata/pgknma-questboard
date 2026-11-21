"""Главните адреси на сайта."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Questboard – администрация"
admin.site.site_title = "Questboard"
admin.site.index_title = "Управление на платформата"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("", include("web.urls")),
]
