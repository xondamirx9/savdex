"""
Вход в админку Django по пропуску (/py/login), база PostgreSQL.

Пропуск собирается здесь по той же схеме, что у PythonBridge::token
(номер, адрес, срок в минуту, HMAC-SHA256 ключом из APP_KEY);
принимает его Django — в отдельном процессе, с тем же APP_KEY и той же
базой, как на сервере. Пользователи заводятся прямо в базе: сотрудник,
заблокированный, с невыданным ещё паролем, удалённый, не сотрудник.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from .pg_admin import свежая_база

PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")
KEY = b"bridge-parity-key-0123456789abcd"
APP_KEY = "base64:" + base64.b64encode(KEY).decode()

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — проверка требует PostgreSQL",
)

ОКРУЖЕНИЕ = {
    **os.environ,
    "APP_KEY": APP_KEY,
    "DB_CONNECTION": "pgsql",
    "DB_URL": АДРЕС,
    "DJANGO_DATABASE_URL": АДРЕС,
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "QUEUE_CONNECTION": "sync",
}

#: Django в отдельном процессе, как на сервере: входит по пропуску и
#: открывает раздел. Печатает ответы JSON-ом
ПРОБА = """
import json, os, sys
import django
django.setup()
import psycopg
from django.test import Client

steps = json.loads(sys.argv[1])
client = Client()
out = []

for step in steps:
    if step[0] == "login":
        r = client.post("/py/login", {"token": step[1]})
    elif step[0] == "sql":
        # Отдельным соединением, как правка из другого процесса: из
        # самого Django запись в users не пропустит предохранитель
        with psycopg.connect(os.environ["DJANGO_DATABASE_URL"], autocommit=True) as c:
            c.execute(step[1])
        out.append(None)
        continue
    else:
        r = client.get(step[1])

    out.append({"status": r.status_code, "location": r.get("Location"),
                "body": r.content.decode()})

print(json.dumps(out, ensure_ascii=False))
"""


@pytest.fixture(scope="module", autouse=True)
def база():
    свежая_база()


def _sql(query: str) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query)

        return курсор.fetchall() if курсор.description else []


def _сотрудник(email: str, **поля: Any) -> int:
    значения = {
        "name": "Анна",
        "email": email,
        "password": "x",
        "is_admin": True,
        "admin_role": "content_manager",
        "status": "active",
        "must_change_password": False,
    } | поля
    столбцы = ", ".join(значения)
    места = ", ".join(["%s"] * len(значения))

    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        соединение.execute("delete from users where email = %s", [email])
        row = соединение.execute(
            f"insert into users ({столбцы}, created_at, updated_at) "
            f"values ({места}, now(), now()) returning id",
            list(значения.values()),
        ).fetchone()

    assert row is not None

    return int(row[0])


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _пропуск(uid: int, next_: str = "/py/admin/", сдвиг: int = 0) -> str:
    """
    Пропуск, как его выдавал PythonBridge::token: JSON без экранирования
    «/», срок — минута от выдачи (сдвиг — выдан в прошлом), подпись —
    HMAC-SHA256 ключом, выведенным из APP_KEY. Адрес не проверяется:
    чужой адрес должен отсечь сам Django.
    """
    payload = _b64(
        json.dumps(
            {
                "uid": uid,
                "next": next_,
                "exp": int(time.time()) + сдвиг + 60,
                "nonce": secrets.token_hex(8),
            },
            separators=(",", ":"),
        ).encode()
    )
    key = hmac.new(KEY, b"savdex-django-bridge-v1", hashlib.sha256).digest()

    return payload + "." + _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def _django(*steps: list[str]) -> list[dict[str, Any]]:
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps(steps)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    return json.loads(вывод)


def test_сотрудник_входит_по_пропуску():
    uid = _сотрудник("anna@savdex.uz", admin_permissions=json.dumps({"grant": ["plans.view"]}))

    вход, раздел = _django(["login", _пропуск(uid, "/py/admin/")], ["get", "/py/admin/"])

    assert вход["status"] == 302 and вход["location"] == "/py/admin/", вход
    assert раздел["status"] == 200, раздел
    assert "Анна" in раздел["body"] and "Контент-менеджер" in раздел["body"]
    # Контент-менеджеру справочники выданы — раздел стран виден
    assert "Страны" in раздел["body"]


@pytest.mark.parametrize(
    "поля",
    [
        pytest.param({"status": "blocked"}, id="заблокирован"),
        pytest.param({"must_change_password": True}, id="не сменил выданный пароль"),
        pytest.param({"is_admin": False}, id="не сотрудник"),
        pytest.param({"deleted_at": "2026-01-01 00:00:00"}, id="удалён"),
    ],
)
def test_кому_нельзя_пропуск_не_помогает(поля):
    uid = _сотрудник("nope@savdex.uz", **поля)

    [вход] = _django(["login", _пропуск(uid)])

    assert вход["status"] == 403, вход


def test_просроченный_пропуск():
    uid = _сотрудник("late@savdex.uz")

    [вход] = _django(["login", _пропуск(uid, сдвиг=-120)])

    assert вход["status"] == 403


def test_пропуск_с_другим_app_key():
    uid = _сотрудник("key@savdex.uz")
    token = _пропуск(uid)

    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps([["login", token]])],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "APP_KEY": "base64:" + base64.b64encode(b"z" * 32).decode(),
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert json.loads(вывод)[0]["status"] == 403


def test_блокировка_действует_сразу():
    """Вошёл, потом заблокировали — следующий же запрос уже не пускает."""
    uid = _сотрудник("later@savdex.uz")

    вход, до, _, после = _django(
        ["login", _пропуск(uid)],
        ["get", "/py/admin/"],
        ["sql", f"update users set status = 'blocked' where id = {uid}"],
        ["get", "/py/admin/"],
    )

    assert вход["status"] == 302
    assert до["status"] == 200
    assert после["status"] == 302 and после["location"].startswith("/py/admin/login/?next=")


def test_чужой_адрес_в_пропуске_не_уводит_с_сайта():
    uid = _сотрудник("next@savdex.uz")

    [вход] = _django(["login", _пропуск(uid, "https://evil.example/py/admin/")])

    assert вход["status"] == 302 and вход["location"] == "/py/admin/"
