"""
Вход в админку Django: пропуск от настоящего Laravel, база PostgreSQL.

Пропуск выдаёт PHP (tests/fixtures/bridge_token.php → PythonBridge),
принимает Django — в отдельном процессе, с тем же APP_KEY и той же
базой, как на сервере. Пользователи заводятся прямо в базе: сотрудник,
заблокированный, с невыданным ещё паролем, удалённый, не сотрудник.

Нужны PHP с зависимостями и PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[2]
PYTHON = Path(__file__).resolve().parents[1]
АДРЕС = os.environ.get("SAVDEX_PARITY_PG_URL", "")
APP_KEY = "base64:" + base64.b64encode(b"bridge-parity-key-0123456789abcd").decode()

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — сравнение требует PHP и PostgreSQL",
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
        # Отдельным соединением, как это сделал бы Laravel: из самого
        # Django запись в users не пропустит предохранитель
        with psycopg.connect(os.environ["DJANGO_DATABASE_URL"], autocommit=True) as c:
            c.execute(step[1])
        out.append(None)
        continue
    else:
        r = client.get(step[1])

    out.append({"status": r.status_code, "location": r.get("Location"),
                "body": r.content.decode()[:2000]})

print(json.dumps(out, ensure_ascii=False))
"""


@pytest.fixture(scope="module", autouse=True)
def база():
    if "test" not in urlparse(АДРЕС).path:
        pytest.fail("SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени — отказываюсь стирать")

    subprocess.run(
        ["php", "artisan", "migrate:fresh", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )


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


def _пропуск(uid: int, next_: str = "/py/admin/", сдвиг: int = 0) -> str:
    return subprocess.run(
        ["php", "python/tests/fixtures/bridge_token.php", str(uid), next_, str(сдвиг)],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


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


def test_сотрудник_входит_по_пропуску_laravel():
    uid = _сотрудник("anna@savdex.uz", admin_permissions=json.dumps({"grant": ["plans.view"]}))

    вход, раздел = _django(["login", _пропуск(uid, "/py/admin/")], ["get", "/py/admin/"])

    assert вход["status"] == 302 and вход["location"] == "/py/admin/", вход
    assert раздел["status"] == 200, раздел
    assert "anna@savdex.uz" in раздел["body"]
    # Права: роль «контент-менеджер» плюс выданные лично «тарифы»
    assert "Справочники" in раздел["body"] and "Тарифы" in раздел["body"]
    assert "Компании" not in раздел["body"]


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


def test_просроченный_пропуск_laravel():
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
    assert после["status"] == 302 and после["location"].startswith("/admin/python?next=")


def test_чужой_адрес_в_пропуске_laravel_не_уводит_с_сайта():
    uid = _сотрудник("next@savdex.uz")

    [вход] = _django(["login", _пропуск(uid, "https://evil.example/py/admin/")])

    assert вход["status"] == 302 and вход["location"] == "/py/admin/"
