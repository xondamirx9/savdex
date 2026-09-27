"""
Разделы админки на Django сквозь настоящую базу — общая часть проверок.

PostgreSQL со схемой Laravel (migrate:fresh), сотрудники с разными
ролями входят по пропуску и работают с разделом так, как работали бы
в браузере. Django запускается отдельным процессом на каждый заход:
настройки читают окружение при запуске, а у pytest-django своя база.

Нужны PHP (миграции) и PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[2]
PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")
KEY = b"countries-admin-key-0123456789ab"
APP_KEY = "base64:" + base64.b64encode(KEY).decode()

нужна_база = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — проверка требует PHP и PostgreSQL",
)

ОКРУЖЕНИЕ = {
    **os.environ,
    "APP_KEY": APP_KEY,
    "DB_CONNECTION": "pgsql",
    "DB_URL": АДРЕС,
    # Под ролью savdex_django, как на боевом: проверяет, что миграции
    # выдали ей права на таблицы раздела. Не задана — под владельцем
    "DJANGO_DATABASE_URL": os.environ.get("SAVDEX_PARITY_DJANGO_URL", АДРЕС),
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "QUEUE_CONNECTION": "sync",
}

#: Django в отдельном процессе: входит по пропуску и выполняет шаги.
#: Печатает ответы JSON-ом
ПРОБА = """
import json, sys
import django
django.setup()
from django.test import Client

import base64
from django.core.files.uploadedfile import SimpleUploadedFile

token, steps = sys.argv[1], json.loads(sys.argv[2])
client = Client(HTTP_X_FORWARDED_FOR="203.0.113.7")
out = [client.post("/py/login", {"token": token}).status_code]

def upload(value):
    # Файл в шаге — {"file": имя, "b64": содержимое}
    if isinstance(value, dict) and "file" in value:
        return SimpleUploadedFile(value["file"], base64.b64decode(value["b64"]))
    return value

for method, url, data in steps:
    data = {k: upload(v) for k, v in (data or {}).items()}
    r = client.get(url) if method == "get" else client.post(url, data)
    body = r.content.decode()
    out.append({"status": r.status_code, "location": r.get("Location"), "body": body})

print(json.dumps(out, ensure_ascii=False))
"""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def пропуск(uid: int) -> str:
    key = hmac.new(KEY, b"savdex-django-bridge-v1", hashlib.sha256).digest()
    body = _b64(
        json.dumps({"uid": uid, "next": "/py/admin/", "exp": int(time.time()) + 60}).encode()
    )

    return body + "." + _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def sql(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query, params or [])

        return курсор.fetchall() if курсор.description else []


def свежая_база() -> None:
    """Схема Laravel с нуля. Только в базе с «test» в имени."""
    if "test" not in urlparse(АДРЕС).path:
        pytest.fail("SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени — отказываюсь стирать")

    subprocess.run(
        ["php", "artisan", "migrate:fresh", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )


def сотрудник(role: str) -> int:
    [(uid,)] = sql(
        "insert into users (name, email, password, is_admin, admin_role, status, "
        "created_at, updated_at) values (%s, %s, 'x', true, %s, 'active', now(), now()) "
        "returning id",
        [f"Сотрудник {role}", f"{role}@savdex.uz", role],
    )

    return int(uid)


def страна(code: str, names: dict[str, str]) -> int:
    [(pk,)] = sql(
        "insert into countries (code, phone_code, currency_code, sort, is_active, created_at, "
        "updated_at) values (%s, '+000', 'XXX', 0, true, now(), now()) returning id",
        [code],
    )
    for locale, name in names.items():
        sql(
            "insert into country_translations (country_id, locale, name, created_at, updated_at) "
            "values (%s, %s, %s, now(), now())",
            [pk, locale, name],
        )

    return int(pk)


def django(
    uid: int,
    *steps: tuple[str, str, dict[str, Any] | None],
    env: dict[str, str] | None = None,
) -> list[Any]:
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, пропуск(uid), json.dumps(steps)],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            **(env or {}),
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return json.loads(вывод.stdout)


def файл(name: str, content: bytes) -> dict[str, str]:
    """Загружаемый файл для шага django()."""
    return {"file": name, "b64": base64.b64encode(content).decode()}


def php(code: str, env: dict[str, str] | None = None) -> str:
    """Выполнить PHP внутри Laravel (tinker) и вернуть вывод."""
    вывод = subprocess.run(
        ["php", "artisan", "tinker", "--execute", code],
        cwd=КОРЕНЬ,
        env={**ОКРУЖЕНИЕ, **(env or {})},
        capture_output=True,
        text=True,
    )
    # Ошибка PHP — в выводе tinker, а не в коде возврата: без него
    # упавшая подготовка данных ничего не объясняет
    assert вывод.returncode == 0, (вывод.stdout + вывод.stderr)[-3000:]

    return вывод.stdout.strip()


def журнал(action: str) -> dict[str, Any]:
    """Последняя строка admin_actions с этим действием."""
    [row] = sql(
        "select user_name, user_role, action, section, subject_type, subject_label, changes, ip "
        "from admin_actions where action = %s order by id desc limit 1",
        [action],
    )
    keys = ("user_name", "user_role", "action", "section", "subject_type", "subject_label")

    return dict(zip(keys, row[:6], strict=True)) | {"changes": row[6], "ip": row[7]}
