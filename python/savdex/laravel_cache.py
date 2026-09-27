"""
Сброс записи в кэше Laravel — Cache::forget() со стороны Django.

Laravel кэширует то, что читает на каждой странице (настройки площадки
на сутки), и сам сбрасывает кэш, когда правит запись. Когда запись
правит Django, сбросить её должен он: иначе сайт сутки показывал бы
старое, а администратор решил бы, что правка не сохранилась.

Хранилище — то же, что у Laravel (CACHE_STORE):

- file (боевой сервер): файл storage/framework/cache/data/aa/bb/<sha1
  ключа>, как FileStore::path(); префикса у файлового хранилища нет;
- database: строка таблицы cache с ключом «<префикс><ключ>». Префикс
  Laravel берёт из CACHE_PREFIX или APP_NAME — в том числе из своего
  .env, которого Django не читает, — поэтому строка ищется по окончанию
  ключа: префикс не важен;
- array и прочее: хранилище живёт в памяти процесса Laravel, сбрасывать
  нечего.

Сверка с настоящим Laravel — tests/test_laravel_cache_parity.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, connection, transaction

from savdex.guards import allowed_writes

#: FLEXIBLE_CREATED_KEY_PREFIX: Cache::flexible() хранит рядом метку
#: создания, и FileStore::forget() удаляет её тоже
_FLEXIBLE = "illuminate:cache:flexible:created:"


def _store() -> str:
    return os.environ.get("CACHE_STORE", "database")


def file_path(key: str) -> Path:
    """FileStore::path(): data/aa/bb/<sha1>."""
    digest = hashlib.sha1(key.encode()).hexdigest()

    return (
        Path(settings.LARAVEL_ROOT)
        / "storage/framework/cache/data"
        / digest[:2]
        / digest[2:4]
        / digest
    )


log = logging.getLogger(__name__)


def forget(key: str) -> bool:
    """
    Cache::forget($key) того хранилища, которым пользуется Laravel.

    Никогда не бросает: правка уже сохранена, и несброшенный кэш — это
    старое значение на сайте до конца суток, а не повод отменить правку.
    Неудача пишется в лог и возвращается как False.
    """
    store = _store()

    try:
        if store == "file":
            for name in (key, _FLEXIBLE + key):
                file_path(name).unlink(missing_ok=True)

        elif store == "database":
            # Своя точка сохранения: ошибка здесь не должна отменить
            # транзакцию, в которой сохранена сама правка
            with transaction.atomic(), allowed_writes("cache"), connection.cursor() as cursor:
                cursor.execute(
                    "delete from cache where right(key, %s) = %s or right(key, %s) = %s",
                    [len(key), key, len(_FLEXIBLE + key), _FLEXIBLE + key],
                )
    except (OSError, DatabaseError):
        log.exception("Кэш Laravel «%s» не сброшен: сайт покажет старое до суток", key)

        return False

    return True
