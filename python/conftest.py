"""
Настройка проверок.

База для тестов — SQLite в памяти, хотя площадка работает на
PostgreSQL. Так можно: предохранители разбирают текст запроса и про
устройство базы ничего не знают, а прогон проверок не должен требовать
поднятого сервера — ни у разработчика, ни в CI.

Подмена здесь, а не в settings.py: настройки для боевой работы не
должны знать о существовании тестов.

Когда дойдём до переноса настоящих запросов, часть проверок придётся
перевести на PostgreSQL: SQLite иначе сортирует кириллицу и иначе
ведёт себя с регистром. Это будет видно по падающим проверкам,
а не по забытой договорённости.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def django_db_modify_db_settings() -> None:
    """Перед созданием тестовой базы — переключить её на SQLite."""
    from django.conf import settings
    from django.db import connections

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

    # Обработчик соединений держит копию настроек: без сброса он
    # продолжит ходить в PostgreSQL по прежнему адресу
    connections.settings = connections.configure_settings(settings.DATABASES)
    del connections["default"]
