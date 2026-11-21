from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="api-health"),
    path("me/", views.MeView.as_view(), name="api-me"),
    # Автоматична документация на API-то
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
