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

# ── Секреты и режим ─────────────────────────────────────────────────

# Своё имя, не APP_KEY: ключ Laravel подписывает куки сессий, и общий
# секрет на два разных алгоритма подписи — способ однажды разлогинить
# всех и не понять почему
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "небезопасный-ключ-для-разработки")

DEBUG = os.environ.get("APP_ENV", "local") not in ("production", "staging")

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

# ── База ────────────────────────────────────────────────────────────


def _database() -> dict[str, Any]:
    """
    Подключение к той же базе, с которой работает Laravel.

    DATABASE_URL — то, что даёт Render. Переменные DB_* — то, что
    стоит в .env у разработчика. Порядок именно такой: на сервере
    выигрывает сервер.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("TARGET_DB_URL")

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

# Ни contenttypes, ни auth, ни sessions: каждое из них хочет свои
# таблицы, а таблицы здесь заводит Laravel. Появятся, когда дойдём
# до этапов 5 и 6.
INSTALLED_APPS = [
    # Через AppConfig, а не просто "savdex": в его ready() включаются
    # предохранители переноса (см. savdex/apps.py)
    "savdex.apps.SavdexConfig",
]

MIDDLEWARE: list[str] = []

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
