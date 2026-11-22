from django.contrib.auth import views as auth_views
from django.urls import path

from accounts.forms import LoginForm

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("notifications/", views.notifications, name="notifications"),
    path("password/", views.QuestboardPasswordChangeView.as_view(), name="password_change"),
    path("school-logo/", views.school_logo, name="school_logo"),
    path("terms/", views.terms, name="terms"),
    path("favicon.ico", views.favicon, name="favicon"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
    path("privacy/", views.privacy, name="privacy"),
    # Мисии
    path("missions/", views.mission_list, name="mission_list"),
    path("missions/new/", views.mission_create, name="mission_create"),
    path("missions/<int:pk>/", views.mission_detail, name="mission_detail"),
    path("missions/<int:pk>/edit/", views.mission_edit, name="mission_edit"),
    path("missions/<int:pk>/hint/", views.mission_hint, name="mission_hint"),
    # Проверка на заявки (учител)
    path("review/", views.review_list, name="review_list"),
    path("claims/<int:pk>/review/", views.review_claim, name="review_claim"),
    # Магазин (ученик) и купени привилегии (учител)
    path("shop/", views.shop, name="shop"),
    path("shop/<int:pk>/buy/", views.shop_buy, name="shop_buy"),
    path("purchases/", views.purchase_list, name="purchase_list"),
    path("purchases/<int:pk>/use/", views.purchase_use, name="purchase_use"),
    # Класация
    path("leaderboard/", views.leaderboard_view, name="leaderboard"),
    # Справки и асистент
    path("reports/", views.reports, name="reports"),
    path("assistant/", views.assistant_chat, name="assistant"),
]
