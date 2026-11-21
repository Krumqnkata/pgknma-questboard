from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views

# Router-ът създава адресите за списък, детайл, създаване и редакция.
router = DefaultRouter()
router.register("missions", views.MissionViewSet, basename="mission")
router.register("claims", views.ClaimViewSet, basename="claim")
router.register("privileges", views.PrivilegeViewSet, basename="privilege")
router.register("purchases", views.PurchaseViewSet, basename="purchase")

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="api-health"),
    path("me/", views.MeView.as_view(), name="api-me"),
    path("me/stats/", views.MyStatsView.as_view(), name="api-my-stats"),
    path("leaderboard/", views.LeaderboardView.as_view(), name="api-leaderboard"),
    path("", include(router.urls)),
    # Автоматична документация на API-то
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]
