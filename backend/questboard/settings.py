"""
Настройки на основното API (Django).

Стойностите, които зависят от компютъра или са тайни, се четат от файла .env
в главната папка на проекта. Правилата на играта НЕ са тук – те са в базата
(модел economy.GameSettings) и се променят от Django admin.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
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
    # Тема за Django admin – трябва да е преди django.contrib.admin
    "unfold",
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
                "web.context_processors.navigation",
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
            # Всяка транзакция заключва базата за писане още в началото,
            # за да не се засекат две едновременни покупки или потвърждения.
            "OPTIONS": {"transaction_mode": "IMMEDIATE"},
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

# При тестовете ползваме бърз (и несигурен) хеш, за да не чакаме при всеки тестов потребител.
# В истинската работа остава сигурният хеш по подразбиране (PBKDF2).
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# При изтекла форма (CSRF) – нашата страница на български вместо стандартната
CSRF_FAILURE_VIEW = "web.views.errors.csrf_failure"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"


# ---------- Език и време ----------
# Интерфейсът е само на български, независимо от езика на браузъра.
LANGUAGE_CODE = "bg"
LANGUAGES = [("bg", "Български")]
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


# ---------- Тема на администрацията (django-unfold) ----------
# Менюто вляво е подредено по задачи, а не по приложения в кода.
# Иконите са имената от Material Symbols: https://fonts.google.com/icons
def _admin_link(name):
    return reverse_lazy(f"admin:{name}_changelist")


UNFOLD = {
    "SITE_TITLE": "Questboard",
    "SITE_HEADER": "Questboard",
    "SITE_SUBHEADER": "Администрация",
    "SITE_SYMBOL": "swords",
    "SITE_URL": "/",
    "ENVIRONMENT": "questboard.admin_config.environment_label",
    "SHOW_HISTORY": True,
    "COLORS": {
        # Индиго – същият цвят като в страниците за ученици и учители
        "primary": {
            "50": "oklch(96.2% .018 272.314)",
            "100": "oklch(93% .034 272.788)",
            "200": "oklch(87% .065 274.039)",
            "300": "oklch(78.5% .115 274.713)",
            "400": "oklch(67.3% .182 276.935)",
            "500": "oklch(58.5% .233 277.117)",
            "600": "oklch(51.1% .262 276.966)",
            "700": "oklch(45.7% .24 277.023)",
            "800": "oklch(39.8% .195 277.366)",
            "900": "oklch(35.9% .144 278.697)",
            "950": "oklch(25.7% .09 281.288)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "items": [
                    {"title": "Табло", "icon": "dashboard", "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": "Игра",
                "separator": True,
                "items": [
                    {"title": "Настройки на играта", "icon": "tune",
                     "link": _admin_link("economy_gamesettings")},
                    {"title": "Нива", "icon": "military_tech", "link": _admin_link("economy_level")},
                    {"title": "Магазин", "icon": "storefront", "link": _admin_link("economy_privilege")},
                ],
            },
            {
                "title": "Мисии",
                "separator": True,
                "items": [
                    {"title": "Мисии", "icon": "flag", "link": _admin_link("missions_mission")},
                    {"title": "Заявки", "icon": "task_alt", "link": _admin_link("missions_claim"),
                     "badge": "questboard.admin_config.pending_claims_badge"},
                ],
            },
            {
                "title": "Хора",
                "separator": True,
                "items": [
                    {"title": "Потребители", "icon": "group", "link": _admin_link("accounts_user")},
                    {"title": "Класове", "icon": "school", "link": _admin_link("accounts_schoolclass")},
                    {"title": "Гилдии", "icon": "shield", "link": _admin_link("accounts_guild")},
                ],
            },
            {
                "title": "Разписание",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Учебни часове", "icon": "calendar_month", "link": _admin_link("timetable_lesson")},
                    {"title": "Кабинети", "icon": "meeting_room", "link": _admin_link("timetable_room")},
                    {"title": "Предмети", "icon": "menu_book", "link": _admin_link("timetable_subject")},
                ],
            },
            {
                "title": "Журнали",
                "separator": True,
                "collapsible": True,
                "items": [
                    {"title": "Движения на XP", "icon": "trending_up", "link": _admin_link("economy_xptransaction")},
                    {"title": "Движения на монети", "icon": "paid", "link": _admin_link("economy_cointransaction")},
                    {"title": "Седмични сметки", "icon": "date_range", "link": _admin_link("economy_coinweek")},
                    {"title": "Покупки", "icon": "shopping_bag", "link": _admin_link("economy_purchase")},
                    {"title": "Ползване на асистента", "icon": "smart_toy",
                     "link": _admin_link("assistant_bridge_assistantlog")},
                    {"title": "Дадени подсказки", "icon": "lightbulb", "link": _admin_link("assistant_bridge_hint")},
                    {"title": "Промени в администрацията", "icon": "history", "link": _admin_link("admin_logentry")},
                ],
            },
        ],
    },
}


# ---------- Услуга на асистента ----------
ASSISTANT_URL = os.getenv("ASSISTANT_URL", "http://127.0.0.1:8001")
ASSISTANT_TOKEN = os.getenv("ASSISTANT_TOKEN", "")
# Колко секунди чакаме асистента, преди да покажем съобщение за грешка.
# Асистентът чака всеки доставчик до 15 s и може да опита и трите.
ASSISTANT_TIMEOUT_SECONDS = 50


# ---------- Сигурност в публикуваната версия ----------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
