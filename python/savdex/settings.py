"""
Настройки Django для SavdEX.

Пока приложение ничего не обслуживает: этап 0 из
`docs/migration-to-python.md` — это каркас, предохранители и проверки,
а не код площадки.

Настройки базы читаются из тех же переменных, что у Laravel. Держать
два набора имён для одной базы значит однажды поменять один и забыть
про другой.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

#: Корень Laravel: Django живёт в его подпапке python/. Нужен для общих
#: с Laravel файлов — кэша (savdex/laravel_cache.py) и публичного диска
LARAVEL_ROOT = Path(os.environ.get("LARAVEL_ROOT", BASE_DIR.parent))

# ── Секреты и режим ─────────────────────────────────────────────────


def _app_key() -> bytes | None:
    """APP_KEY Laravel байтами — так же, как его читает Encrypter::parseKey."""
    raw = os.environ.get("APP_KEY", "")

    if raw.startswith("base64:"):
        import base64
        import binascii

        try:
            return base64.b64decode(raw[7:], validate=True)
        except (binascii.Error, ValueError):
            return None

    return raw.encode() if raw else None


def _derived(label: str) -> str | None:
    """
    Отдельный ключ под отдельную задачу, выведенный из APP_KEY.

    Не сам APP_KEY: ключ Laravel шифрует его куки, и общий секрет на
    два разных алгоритма — способ однажды разлогинить всех и не понять
    почему. HMAC с меткой даёт независимый ключ, а заводить на Render
    ещё одну секретную переменную не нужно: APP_KEY там уже есть.
    """
    import hashlib
    import hmac

    key = _app_key()

    return hmac.new(key, label.encode(), hashlib.sha256).hexdigest() if key else None


#: Подписывает куку входа в Django-админку. Своя переменная сильнее,
#: иначе — выведенный из APP_KEY; без обоих — ключ разработчика,
#: и тогда вход в админку отключён (savdex/bridge.py): подпись известным
#: всем ключом подделал бы кто угодно
SECRET_KEY = (
    os.environ.get("DJANGO_SECRET_KEY")
    or _derived("savdex-django-secret-key-v1")
    or "небезопасный-ключ-для-разработки"
)
SECRET_KEY_IS_REAL = bool(os.environ.get("DJANGO_SECRET_KEY") or _app_key())

DEBUG = os.environ.get("APP_ENV", "local") not in ("production", "staging")

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

# За Apache и балансировщиком Render: HTTPS снимается снаружи, до Django
# запрос доходит по HTTP. Какой был исходный протокол, говорит заголовок
# X-Forwarded-Proto от Render — Apache передаёт его как есть. Без этого
# Django считал бы каждый запрос небезопасным и строил ссылки на http://
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── База ────────────────────────────────────────────────────────────


def _database() -> dict[str, Any]:
    """
    Подключение к той же базе, с которой работает Laravel.

    DJANGO_DATABASE_URL — собственная роль Python в PostgreSQL (чтение
    всего, запись только того, что заявлено в guards.SHARED_WRITES);
    Laravel эту переменную не читает, поэтому на Render её можно задать
    для всей службы, не трогая сайт. DATABASE_URL — адрес, переданный
    явно, или то, что даёт хостинг. Переменные DB_* — то, что стоит
    в .env у разработчика. Порядок именно такой: чем уже и явнее, тем
    раньше.
    """
    url = (
        os.environ.get("DJANGO_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("TARGET_DB_URL")
    )

    if url:
        import dj_database_url

        return dict(dj_database_url.parse(url, conn_max_age=600))

    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "NAME": os.environ.get("DB_DATABASE", "savdex"),
        "USER": os.environ.get("DB_USERNAME", "savdex"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "CONN_MAX_AGE": 600,
    }


DATABASES = {"default": _database()}

# Правило 4.2: схему базы меняет только Laravel
DATABASE_ROUTERS = ["savdex.guards.LaravelOwnsSchema"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Приложения ──────────────────────────────────────────────────────

# Админка Django (этап 2) — со своими приложениями admin, auth,
# contenttypes и messages, но без их таблиц: таблицы заводит только
# Laravel. Пользователь — тот, кто пришёл по пропуску из Laravel
# (savdex/bridge.py), журнал — admin_actions, а не django_admin_log;
# места, где админка Django полезла бы в свои таблицы, закрыты
# в savdex/adminsite.py. Своих сессий нет: вход — подписанная кука.
INSTALLED_APPS = [
    # Через AppConfig, а не просто "savdex": в его ready() включаются
    # предохранители переноса (см. savdex/apps.py)
    "savdex.apps.SavdexConfig",
    "savdex.geo.apps.GeoConfig",
    "savdex.catalogs.apps.CatalogsConfig",
    "savdex.billing.apps.BillingConfig",
    "savdex.site.apps.SiteConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Стили и скрипты админки — из самого Django, без отдельного сервера
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # Сообщения «сохранено» живут в куке: таблицы сессий нет
    "django.contrib.messages.middleware.MessageMiddleware",
    # Кто открыл раздел админки на Django (вход — пропуском из Laravel)
    "savdex.adminpanel.AdminMiddleware",
]

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "savdex" / "templates"],
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

# Проверки админки Django требуют промежуточных слоёв входа и сессий
# Django. Их здесь нет намеренно: вход — пропуском из Laravel, а
# request.user ставит savdex.adminpanel.AdminMiddleware
SILENCED_SYSTEM_CHECKS = ["admin.E408", "admin.E410"]

STATIC_URL = "/py/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Кука CSRF — только для адресов Django и со своим именем: у Laravel
# своя (XSRF-TOKEN), делить им нечего
CSRF_COOKIE_NAME = "savdex_py_csrf"
CSRF_COOKIE_PATH = "/py/"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"

ROOT_URLCONF = "savdex.urls"
WSGI_APPLICATION = "savdex.wsgi.application"

# ── Язык и время ────────────────────────────────────────────────────

LANGUAGE_CODE = "ru"

# То же, что App\Support\Business::DEFAULT_TIMEZONE. Расхождение
# сдвинуло бы границы суток в отчётах на пять часов
TIME_ZONE = os.environ.get("BUSINESS_TIMEZONE", "Asia/Tashkent")

USE_I18N = True
USE_TZ = True

# ── Пароли ──────────────────────────────────────────────────────────

# Laravel хранит пароли bcrypt (приведение 'password' => 'hashed'
# в App\Models\User, своего config/hashing.php в проекте нет — значит
# работает умолчание фреймворка). Перехешировать нечего: исходных
# паролей мы не знаем. Понадобится на этапе 5.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# ── Журнал ──────────────────────────────────────────────────────────


def _log_level() -> str:
    """
    Уровень журнала из LOG_LEVEL — той же переменной, что у Laravel.

    Соглашения у двух половин разные: Laravel пишет уровень строчными
    и знает восемь уровней PSR-3 («debug», «notice», «emergency»), а
    журнал Python — только пять и прописными. «debug» как есть ронял
    Django ещё на старте: «Unable to configure root logger». Нашлось
    первым же запуском Python-выгрузки из PHP, которая передаёт своё
    окружение целиком.
    """
    level = os.environ.get("LOG_LEVEL", "info").strip().lower()

    return {
        "debug": "DEBUG",
        "info": "INFO",
        "notice": "INFO",
        "warning": "WARNING",
        "error": "ERROR",
        "critical": "CRITICAL",
        "alert": "CRITICAL",
        "emergency": "CRITICAL",
    }.get(level, "INFO")


# В stderr, как у Laravel (LOG_CHANNEL=stderr): на Render видно
# в одном потоке с логами PHP, и порядок событий не надо восстанавливать
# по двум разным местам
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"stderr": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["stderr"], "level": _log_level()},
}
