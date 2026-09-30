"""
Шаг 67: вход в админку на Django (savdex/adminlogin.py) вместо Filament.

Настоящая база PostgreSQL, Django в отдельном процессе со своей сессией
Laravel. Проверяется:

- сотрудник входит почтой в любом регистре и попадает туда, куда шёл;
  вход пишет сессию Laravel — он вошёл и на сайт;
- неверный пароль, не сотрудник, заблокированный — «неверная почта или
  пароль», сессии нет;
- с выданным паролем — на его смену (RequirePasswordChange);
- вошедший на сайт сотрудник проходит в админку без повторного входа;
  не сотруднику — 403;
- выход — из админки и с сайта разом;
- больше пяти попыток в минуту — 429.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
import time
from typing import Any

import pytest

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база

pytestmark = нужна_база

ПАРОЛЬ = "Tashkent-2026!"

#: Django с чистым браузером: шаги — (метод, адрес, данные); у POST на
#: страницу входа токен сессии подставляется со страницы входа
ПРОБА = """
import json, re, sys
import django
django.setup()
from django.test import Client
from savdex import bridge

steps = json.loads(sys.argv[1])
client = Client(HTTP_X_FORWARDED_FOR=sys.argv[2])
out = []
token = ""

for method, url, data in steps:
    if method == "sql-revoke":
        # Права снимает владелец базы: у роли Django на users их нет
        import os, psycopg
        with psycopg.connect(os.environ["DB_URL"], autocommit=True) as db:
            db.execute("update users set is_admin = false where email = 'buyer@savdex.uz'")
        out.append({})
        continue
    if method == "drop-admin-cookie":
        client.cookies.pop(bridge.COOKIE, None)
        out.append({})
        continue
    if method == "post" and url.startswith("/py/admin/login/"):
        data = {"_token": token, **(data or {})}
    r = client.get(url) if method == "get" else client.post(url, data or {})
    body = r.content.decode(errors="replace")
    found = re.search(r'name="_token" value="([^"]+)"', body)
    if found:
        token = found.group(1)
    out.append({
        "status": r.status_code,
        "location": r.get("Location"),
        "body": body,
        "admin_cookie": bool(r.cookies.get(bridge.COOKIE) and r.cookies[bridge.COOKIE].value),
    })

print(json.dumps(out, ensure_ascii=False))
"""


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    import bcrypt

    hashed = bcrypt.hashpw(ПАРОЛЬ.encode(), bcrypt.gensalt(4)).decode().replace("$2b$", "$2y$")
    ids: dict[str, int] = {}

    for name, is_admin, role, status, must_change in (
        ("admin", True, "content_manager", "active", False),
        ("fresh", True, "support", "active", True),
        ("blocked", True, "support", "blocked", False),
        ("buyer", False, None, "active", False),
    ):
        [(uid,)] = sql(
            "insert into users (name, email, password, is_admin, admin_role, status, "
            "must_change_password, email_verified_at, created_at, updated_at) values "
            "(%s, %s, %s, %s, %s, %s, %s, now(), now(), now()) returning id",
            [name, f"{name}@savdex.uz", hashed, is_admin, role, status, must_change],
        )
        ids[name] = int(uid)

    return ids


_адреса = itertools.count(10)


def браузер(*steps: list[Any], ip: str | None = None) -> list[dict[str, Any]]:
    # Свой адрес на каждый браузер: счётчик частоты считает по IP
    ip = ip or f"203.0.113.{next(_адреса)}"
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps(list(steps)), ip],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "PYTHONPATH": str(PYTHON),
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            # Как на боевом: вход пишет сессию Laravel в таблицу sessions,
            # счётчик частоты — в файловый кэш
            "SESSION_DRIVER": "database",
            "CACHE_STORE": "file",
        },
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    return list(json.loads(вывод.splitlines()[-1]))


def вход(email: str, password: str = ПАРОЛЬ, next_: str = "/py/admin/geo/country/") -> list[Any]:
    return ["post", "/py/admin/login/", {"email": email, "password": password, "next": next_}]


def test_вход_сотрудника_и_сессия_сайта(люди):
    sql("truncate login_attempts")
    без_входа, форма, ответ, раздел, кто, снова, _, без_куки = браузер(
        ["get", "/py/admin/geo/country/", None],
        ["get", "/py/admin/login/?next=/py/admin/geo/country/", None],
        вход("  Admin@SavdEx.uz "),
        ["get", "/py/admin/", None],
        ["get", "/py/whoami", None],
        ["get", "/py/admin/", None],
        ["drop-admin-cookie", "", None],
        ["get", "/py/admin/", None],
    )

    assert без_входа["status"] == 302
    assert без_входа["location"] == "/py/admin/login/?next=/py/admin/geo/country/"
    assert форма["status"] == 200 and 'name="_token"' in форма["body"]
    assert ответ["status"] == 302 and ответ["location"] == "/py/admin/geo/country/"
    assert ответ["admin_cookie"]
    assert раздел["status"] == 200 and "admin" in раздел["body"]
    # Вход в админку — вход и на сайт: одна сессия Laravel
    assert str(люди["admin"]) in кто["body"]
    assert снова["status"] == 200
    # Кука админки пропала, сессия сайта осталась — пускает и выдаёт куку
    assert без_куки["status"] == 200 and без_куки["admin_cookie"]


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("admin@savdex.uz", "wrong-password"),
        ("buyer@savdex.uz", ПАРОЛЬ),
        ("blocked@savdex.uz", ПАРОЛЬ),
        ("nobody@savdex.uz", ПАРОЛЬ),
    ],
)
def test_отказ_без_подсказки(люди, email, password):
    sql("truncate login_attempts")
    _, ответ, кто = браузер(
        ["get", "/py/admin/login/", None],
        вход(email, password),
        ["get", "/py/whoami", None],
    )

    assert ответ["status"] == 422 and "Неверная почта или пароль." in ответ["body"]
    assert not ответ["admin_cookie"]
    assert json.loads(кто["body"])["authenticated"] is False


def test_выданный_пароль_на_смену(люди):
    sql("truncate login_attempts")
    _, ответ, раздел = браузер(
        ["get", "/py/admin/login/", None],
        вход("fresh@savdex.uz"),
        ["get", "/py/admin/", None],
    )

    assert ответ["status"] == 302 and ответ["location"] == "/password/change"
    assert not ответ["admin_cookie"]
    # Вошёл на сайт, но в админку — только после смены пароля
    assert раздел["status"] == 302 and раздел["location"] == "/password/change"


def test_права_сняли_сессия_сайта_осталась_403(люди):
    sql("truncate login_attempts")
    sql("update users set is_admin = true where id = %s", [люди["buyer"]])
    try:
        _, ответ, _, _, раздел = браузер(
            ["get", "/py/admin/login/", None],
            вход("buyer@savdex.uz"),
            ["sql-revoke", "", None],
            ["drop-admin-cookie", "", None],
            ["get", "/py/admin/", None],
        )
    finally:
        sql("update users set is_admin = false where id = %s", [люди["buyer"]])

    assert ответ["status"] == 302
    # Вошёл на сайт, но сотрудником больше не числится — 403, а не круг входа
    assert раздел["status"] == 403 and "нет доступа к админке" in раздел["body"]


def test_выход_из_админки_и_с_сайта(люди):
    sql("truncate login_attempts")
    _, ответ, выход, кто, раздел = браузер(
        ["get", "/py/admin/login/", None],
        вход("admin@savdex.uz"),
        ["post", "/py/admin/logout/", None],
        ["get", "/py/whoami", None],
        ["get", "/py/admin/", None],
    )

    assert ответ["status"] == 302
    assert выход["status"] == 302 and выход["location"] == "/py/admin/login/"
    assert str(люди["admin"]) not in кто["body"]
    assert раздел["status"] == 302 and раздел["location"].startswith("/py/admin/login/")


def test_частота_попыток(люди):
    sql("truncate login_attempts")
    ответы = браузер(
        ["get", "/py/admin/login/", None],
        *[вход("admin@savdex.uz", f"wrong-{n}") for n in range(6)],
        # Свой адрес на каждый запуск: счётчик живёт минуту в общем кэше
        ip=f"198.51.100.{int(time.time()) % 250 + 1}",
    )

    assert [r["status"] for r in ответы[1:6]] == [422] * 5
    assert ответы[6]["status"] == 429
