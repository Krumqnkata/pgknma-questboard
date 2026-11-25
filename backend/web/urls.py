from django.contrib.auth import views as auth_views
from django.urls import path, re_path

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
    path("sponsor-logo/<str:name>", views.sponsor_logo, name="sponsor_logo"),
    path("terms/", views.terms, name="terms"),
    path("favicon.ico", views.favicon, name="favicon"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
    path("privacy/", views.privacy, name="privacy"),
    # Мисии
    path("missions/", views.mission_list, name="mission_list"),
    path("missions/new/", views.mission_create, name="mission_create"),
    path("homework/new/", views.homework_create, name="homework_create"),
    path("missions/<int:pk>/", views.mission_detail, name="mission_detail"),
    path("missions/<int:pk>/edit/", views.mission_edit, name="mission_edit"),
    path("missions/<int:pk>/hint/", views.mission_hint, name="mission_hint"),
    path("missions/<int:pk>/extend/", views.mission_extend, name="mission_extend"),
    path("missions/<int:pk>/leave-team/", views.team_leave, name="team_leave"),
    path("mission-files/<int:pk>/", views.mission_file, name="mission_file"),
    # Проверка на заявки (учител)
    path("review/", views.review_list, name="review_list"),
    path("review/approve/", views.review_bulk, name="review_bulk"),
    path("claims/<int:pk>/review/", views.review_claim, name="review_claim"),
    path("evidence/<int:pk>/", views.evidence_file, name="evidence_file"),
    path("claims/<int:pk>/undo/", views.claim_undo, name="claim_undo"),
    # Магазин (ученик) и купени привилегии (учител)
    path("shop/", views.shop, name="shop"),
    path("shop/<int:pk>/buy/", views.shop_buy, name="shop_buy"),
    path("purchases/", views.purchase_list, name="purchase_list"),
    path("purchases/<int:pk>/use/", views.purchase_use, name="purchase_use"),
    # Класация
    path("leaderboard/", views.leaderboard_view, name="leaderboard"),
    path("rewards/", views.rewards, name="rewards"),
    # Гилдии и тестове
    path("guilds/", views.guild_list, name="guild_list"),
    path("guilds/<int:pk>/main/", views.guild_main, name="guild_main"),
    path("guilds/<int:pk>/leave/", views.guild_leave, name="guild_leave"),
    path("tests/start/", views.test_start, name="test_start"),
    path("tests/attempt/<int:pk>/", views.test_attempt, name="test_attempt"),
    path("tests/attempt/<int:pk>/left/", views.test_left, name="test_left"),
    path("tests/", views.test_list, name="test_list"),
    path("tests/new/", views.test_create, name="test_create"),
    path("tests/<int:pk>/", views.test_edit, name="test_edit"),
    path("tests/<int:pk>/open/", views.session_open, name="session_open"),
    path("tests/sessions/<int:pk>/", views.test_session, name="test_session"),
    # Справки и асистент
    path("reports/", views.reports, name="reports"),
    path("assistant/", views.assistant_chat, name="assistant"),
    # Шегата за ботовете, които търсят WordPress (web/views/not_wordpress.py)
    re_path(r"^(?:wp-admin|wp-content|wp-includes|wp-json)(?:/(?P<rest>.*))?$", views.not_wordpress,
            name="not_wordpress"),
    re_path(r"^(?:wp-login\.php|wp-login/?|xmlrpc\.php|wp-config\.php)$", views.not_wordpress),
]
