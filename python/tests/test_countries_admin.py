"""
Раздел «Страны» админки на Django — сквозь настоящую базу.

PostgreSQL со схемой Laravel (migrate:fresh), сотрудники с разными
ролями входят по пропуску и работают с разделом так, как работали бы
в браузере: список, заведение, правка, удаление. Проверяются права
(AdminAccess), правила Country (код строчными, запрет удаления при
ссылках, русское название) и строки журнала admin_actions.

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

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — проверка требует PHP и PostgreSQL",
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

#: Django в отдельном процессе: входит по пропуску и выполняет шаги.
#: Печатает ответы JSON-ом
ПРОБА = """
import json, sys
import django
django.setup()
from django.test import Client

token, steps = sys.argv[1], json.loads(sys.argv[2])
client = Client(HTTP_X_FORWARDED_FOR="203.0.113.7")
out = [client.post("/py/login", {"token": token}).status_code]

for method, url, data in steps:
    r = client.get(url) if method == "get" else client.post(url, data)
    body = r.content.decode()
    out.append({"status": r.status_code, "location": r.get("Location"), "body": body})

print(json.dumps(out, ensure_ascii=False))
"""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _пропуск(uid: int) -> str:
    key = hmac.new(KEY, b"savdex-django-bridge-v1", hashlib.sha256).digest()
    body = _b64(
        json.dumps({"uid": uid, "next": "/py/admin/", "exp": int(time.time()) + 60}).encode()
    )

    return body + "." + _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def _sql(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query, params or [])

        return курсор.fetchall() if курсор.description else []


def _сотрудник(role: str) -> int:
    [(uid,)] = _sql(
        "insert into users (name, email, password, is_admin, admin_role, status, "
        "created_at, updated_at) values (%s, %s, 'x', true, %s, 'active', now(), now()) "
        "returning id",
        [f"Сотрудник {role}", f"{role}@savdex.uz", role],
    )

    return int(uid)


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    if "test" not in urlparse(АДРЕС).path:
        pytest.fail("SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени — отказываюсь стирать")

    subprocess.run(
        ["php", "artisan", "migrate:fresh", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )

    [(uz,)] = _sql(
        "insert into countries (code, phone_code, currency_code, sort, is_active, created_at, "
        "updated_at) values ('uz', '+998', 'UZS', 0, true, now(), now()) returning id"
    )
    for locale, name in (("ru", "Узбекистан"), ("en", "Uzbekistan")):
        _sql(
            "insert into country_translations (country_id, locale, name, created_at, updated_at) "
            "values (%s, %s, %s, now(), now())",
            [uz, locale, name],
        )
    _sql(
        "insert into cities (country_id, slug, created_at, updated_at) "
        "values (%s, 'tashkent', now(), now())",
        [uz],
    )

    return {
        role: _сотрудник(role) for role in ("superadmin", "content_manager", "moderator", "sales")
    }


def _django(uid: int, *steps: tuple[str, str, dict[str, Any] | None]) -> list[Any]:
    вывод = subprocess.run(
        [sys.executable, "-c", ПРОБА, _пропуск(uid), json.dumps(steps)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return json.loads(вывод.stdout)


def _форма(
    code: str, names: dict[str, str], *, country_id: int | None = None, existing: int = 0
) -> dict[str, Any]:
    """Поля формы страны вместе с формами переводов — как их шлёт браузер."""
    data: dict[str, Any] = {
        "code": code,
        "phone_code": "+996",
        "currency_code": "KGS",
        "sort": "5",
        "is_active": "on",
        "translations-TOTAL_FORMS": str(len(names)),
        "translations-INITIAL_FORMS": str(existing),
        "translations-MIN_NUM_FORMS": "1",
        "translations-MAX_NUM_FORMS": "5",
    }

    ids = {}
    if country_id is not None:
        ids = dict(
            _sql("select locale, id from country_translations where country_id = %s", [country_id])
        )

    for i, (locale, name) in enumerate(names.items()):
        data[f"translations-{i}-locale"] = locale
        data[f"translations-{i}-name"] = name
        if locale in ids:
            data[f"translations-{i}-id"] = str(ids[locale])
            data[f"translations-{i}-country"] = str(country_id)

    return data


def _журнал(action: str) -> dict[str, Any]:
    [row] = _sql(
        "select user_name, user_role, action, section, subject_type, subject_label, changes, ip "
        "from admin_actions where action = %s order by id desc limit 1",
        [action],
    )
    keys = ("user_name", "user_role", "action", "section", "subject_type", "subject_label")

    return dict(zip(keys, row[:6], strict=True)) | {"changes": row[6], "ip": row[7]}


LIST = "/py/admin/geo/country/"
ADD = "/py/admin/geo/country/add/"


def test_список_и_права_на_просмотр(люди):
    вход, список = _django(люди["moderator"], ("get", LIST, None))

    assert вход == 302
    assert список["status"] == 200
    assert "Узбекистан · UZ" in список["body"]
    assert "1 из 5" not in список["body"] and "2 из 5" in список["body"]

    # Модератор смотрит, но не заводит
    _, заведение = _django(люди["moderator"], ("get", ADD, None))
    assert заведение["status"] == 403

    # Отделу продаж справочники не выданы
    _, чужой = _django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_страны_и_журнал(люди):
    _, ответ = _django(
        люди["content_manager"],
        ("post", ADD, _форма(" KG ", {"ru": "Кыргызстан", "en": "Kyrgyzstan"})),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    [(code, _phone)] = _sql("select code, phone_code from countries where phone_code = '+996'")
    assert code == "kg"

    names = dict(
        _sql(
            "select locale, name from country_translations t join countries c "
            "on c.id = t.country_id where c.code = 'kg'"
        )
    )
    assert names == {"ru": "Кыргызстан", "en": "Kyrgyzstan"}

    запись = _журнал("created")
    assert запись["user_name"] == "Сотрудник content_manager"
    assert запись["user_role"] == "content_manager"
    assert запись["section"] == "catalogs"
    assert запись["subject_type"] == "App\\Models\\Country"
    assert запись["subject_label"] == "kg"
    assert запись["ip"] == "203.0.113.7"
    after = запись["changes"]["after"]
    assert after["code"] == "kg" and after["name:ru"] == "Кыргызстан"
    assert "created_at" not in after and "updated_at" not in after


def test_повтор_кода_в_другом_регистре_не_проходит(люди):
    _, ответ = _django(люди["content_manager"], ("post", ADD, _форма("UZ", {"ru": "Дубль"})))

    assert ответ["status"] == 200
    assert "Страна с таким кодом уже есть" in ответ["body"]
    assert _sql("select count(*) from countries where code = 'uz'") == [(1,)]


def test_без_русского_названия_не_сохраняется(люди):
    _, ответ = _django(люди["content_manager"], ("post", ADD, _форма("tj", {"en": "Tajikistan"})))

    assert ответ["status"] == 200
    assert "Нужно русское название" in ответ["body"]
    assert _sql("select count(*) from countries where code = 'tj'") == [(0,)]


def test_правка_и_переименование_попадают_в_журнал(люди):
    [(kg,)] = _sql("select id from countries where code = 'kg'")
    данные = _форма("kg", {"ru": "Киргизия", "en": "Kyrgyzstan"}, country_id=kg, existing=2)
    данные["phone_code"] = "+9960"

    _, ответ = _django(люди["content_manager"], ("post", f"{LIST}{kg}/change/", данные))

    assert ответ["status"] == 302, ответ["body"][:3000]
    запись = _журнал("updated")
    assert запись["changes"] == {
        "before": {"phone_code": "+996", "name:ru": "Кыргызстан"},
        "after": {"phone_code": "+9960", "name:ru": "Киргизия"},
    }


def test_удаление(люди):
    [(kg,)] = _sql("select id from countries where code = 'kg'")
    [(uz,)] = _sql("select id from countries where code = 'uz'")

    # Контент-менеджеру удаление не выдано
    _, чужое = _django(люди["content_manager"], ("post", f"{LIST}{kg}/delete/", {"post": "yes"}))
    assert чужое["status"] == 403

    # На Узбекистан ссылается город — удалить нельзя даже суперадмину
    _, занятая = _django(люди["superadmin"], ("post", f"{LIST}{uz}/delete/", {"post": "yes"}))
    assert занятая["status"] == 403
    assert _sql("select count(*) from countries where id = %s", [uz]) == [(1,)]

    # Свободную — можно, вместе с переводами; удаление — в журнале
    _, свободная = _django(люди["superadmin"], ("post", f"{LIST}{kg}/delete/", {"post": "yes"}))
    assert свободная["status"] == 302
    assert _sql("select count(*) from countries where id = %s", [kg]) == [(0,)]
    assert _sql("select count(*) from country_translations where country_id = %s", [kg]) == [(0,)]
    assert _журнал("deleted")["subject_label"] == "kg"


def test_правка_формы_показывает_почему_нельзя_удалить(люди):
    [(uz,)] = _sql("select id from countries where code = 'uz'")

    _, форма = _django(люди["superadmin"], ("get", f"{LIST}{uz}/change/", None))

    assert форма["status"] == 200
    assert "Нельзя, на страну ссылаются: города — 1" in форма["body"]


def test_резюме_тоже_удерживает_страну(люди):
    """
    Резюме ссылаются на страну, но PHP-версия их не считала: удаление
    страны молча обнуляло её у резюме. Теперь резюме удерживают страну
    в обеих половинах.
    """
    [(tj,)] = _sql(
        "insert into countries (code, phone_code, currency_code, created_at, updated_at) "
        "values ('tj', '+992', 'TJS', now(), now()) returning id"
    )
    _sql(
        "insert into resumes (user_id, title, country_id, created_at, updated_at) "
        "values (%s, 'Инженер', %s, now(), now())",
        [люди["sales"], tj],
    )

    _, форма, удаление = _django(
        люди["superadmin"],
        ("get", f"{LIST}{tj}/change/", None),
        ("post", f"{LIST}{tj}/delete/", {"post": "yes"}),
    )

    assert "Нельзя, на страну ссылаются: резюме — 1" in форма["body"]
    assert удаление["status"] == 403
    assert _sql("select count(*) from countries where id = %s", [tj]) == [(1,)]
