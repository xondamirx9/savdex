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

import fcntl
import hashlib
import logging
import os
import time
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, connection, transaction

from savdex.guards import allowed_writes
from savdex.web.currency import unserialize

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


# ── Файловое хранилище: чтение и запись, как FileStore ──────────────
#
# Нужно для общих с Laravel счётчиков (ограничение частоты, пометки
# «уже посчитан» у статистики): одна запись — один файл, первые 10 знаков
# — срок жизни (время Unix), дальше — значение в serialize() PHP.

#: FileStore::expiration: «навсегда» — 9999999999
FOREVER = 9_999_999_999


def is_file_store() -> bool:
    return _store() == "file"


#: Что кладёт в кэш Django: счётчики, флаги, строки и массивы (код почты)
Value = int | bool | str | None | dict[str | int, "Value"]


def _serialize(value: Value) -> bytes:
    """serialize() PHP: целое, логическое, строка, null и массив."""
    if value is None:
        return b"N;"

    if isinstance(value, bool):
        return b"b:1;" if value else b"b:0;"

    if isinstance(value, int):
        return f"i:{value};".encode()

    if isinstance(value, str):
        data = value.encode()

        return b's:%d:"%b";' % (len(data), data)

    parts = [
        (f"i:{k};".encode() if isinstance(k, int) else _serialize(k)) + _serialize(v)
        for k, v in value.items()
    ]

    return b"a:%d:{%b}" % (len(parts), b"".join(parts))


def _expiration(seconds: int) -> int:
    at = int(time.time()) + seconds

    return FOREVER if seconds == 0 or at > FOREVER else at


def _payload(raw: bytes) -> tuple[object, int] | None:
    """(значение, срок) из содержимого файла; истёк или испорчен — None."""
    try:
        expire = int(raw[:10])
        value = unserialize(raw[10:])
    except ValueError:
        return None

    return None if time.time() >= expire else (value, expire)


def get(key: str) -> object:
    """Cache::get($key): значение или None — нет, истёк, не файловое хранилище."""
    if not is_file_store():
        return None

    try:
        payload = _payload(file_path(key).read_bytes())
    except OSError:
        return None

    return None if payload is None else payload[0]


def _write(path: Path, content: bytes) -> None:
    """Files::put(…, lock: true): запись под исключительной блокировкой."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # «a+b»: открыть, не обрезая, — обрезка только под блокировкой
    with open(path, "a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(content)
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)


def put(key: str, value: Value, seconds: int) -> None:
    """Cache::put: перезаписать значение со сроком."""
    _write(file_path(key), str(_expiration(seconds)).rjust(10, "0").encode() + _serialize(value))


def add(key: str, value: int | bool, seconds: int) -> bool:
    """
    Cache::add: записать, только если записи нет или она истекла.

    Как FileStore::add — файл открывается без обрезки, под исключительной
    блокировкой читается срок, и только потом решается, писать ли.
    """
    path = file_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        expire = handle.read(10)

        try:
            alive = expire != b"" and time.time() < int(expire)
        except ValueError:
            alive = False

        if not alive:
            handle.seek(0)
            handle.truncate()
            handle.write(str(_expiration(seconds)).rjust(10, "0").encode() + _serialize(value))
            handle.flush()

        fcntl.flock(handle, fcntl.LOCK_UN)

    return not alive


def increment(key: str, amount: int = 1) -> int:
    """
    FileStore::increment: прочитать, прибавить, записать с тем же сроком.

    Без блокировки между чтением и записью — как у Laravel: счётчик
    частоты допускает гонку в одну единицу.
    """
    try:
        payload = _payload(file_path(key).read_bytes())
    except OSError:
        payload = None

    current, expire = payload if payload is not None else (0, None)
    value = _to_int(current) + amount
    seconds = 0 if expire is None else max(0, expire - int(time.time()))
    put(key, value, seconds)

    return value


def _to_int(value: object) -> int:
    """(int) PHP для значения из кэша."""
    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int | float):
        return int(value)

    try:
        return int(float(str(value)))
    except ValueError:
        return 0
