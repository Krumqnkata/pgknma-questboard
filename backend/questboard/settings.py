"""
Настройки на основното API (Django).

Стойностите, които зависят от компютъра или са тайни, се четат от файла .env
в главната папка на проекта. Правилата на играта НЕ са тук – те са в базата
(модел economy.GameSettings) и се променят от Django admin.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# backend/ – папката с manage.py
BASE_DIR = Path(__file__).resolve().parent.parent
# Главната папка на проекта, където е .env
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")


def env_bool(name, default=False):
    """Чете True/False от .env (приема True, true, 1, yes)."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    """Чете списък, разделен със запетаи, от .env."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "samo-za-razrabotka-ne-se-polzva-v-publikuvanata-versia"
    else:
        raise ImproperlyConfigured("Липсва DJANGO_SECRET_KEY в .env")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Външни библиотеки
    "rest_framework",
    "drf_spectacular",
    # Нашите приложения
    "accounts",
    "missions",
    "economy",
    "timetable",
    "assistant_bridge",
    "api",
    "web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "questboard.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "questboard.wsgi.application"


# ---------- База данни ----------
# По време на разработка – SQLite (файл, нищо не се инсталира).
# В публикуваната версия – MySQL (DB_ENGINE=mysql в .env).
if os.getenv("DB_ENGINE", "sqlite") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "questboard"),
            "USER": os.getenv("DB_USER", "questboard"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            # utf8mb4 – за да се пазят правилно кирилица и емоджита
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------- Потребители и вход ----------
# Собствен модел на потребител: вход с имейл и поле за роля (виж accounts/models.py)
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"


# ---------- Език и време ----------
LANGUAGE_CODE = "bg"
TIME_ZONE = "Europe/Sofia"
USE_I18N = True
USE_TZ = True


# ---------- Статични файлове (CSS, JavaScript) ----------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------- REST API ----------
# Страниците и чатът са на същия адрес като API-то, затова ползваме
# сесията от входа (с CSRF защита) вместо отделни токени.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Questboard API",
    "DESCRIPTION": "Основно API на Questboard: мисии, точки, монети, магазин и справки.",
    "VERSION": "0.1.0",
}


# ---------- Услуга на асистента ----------
ASSISTANT_URL = os.getenv("ASSISTANT_URL", "http://127.0.0.1:8001")
ASSISTANT_TOKEN = os.getenv("ASSISTANT_TOKEN", "")
# Колко секунди чакаме асистента, преди да покажем съобщение за грешка
ASSISTANT_TIMEOUT_SECONDS = 10


# ---------- Сигурност в публикуваната версия ----------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
