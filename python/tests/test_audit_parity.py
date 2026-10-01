"""
Журнал действий: строка, которую пишет savdex.audit.record.

Запись делается в отдельном процессе Django, как на сервере, и строка
в admin_actions проверяется целиком — та же, что писал AdminLog::record
у Laravel: автор (имя — снимок не длиннее 120 знаков, без автора —
«консоль»), роль, действие, раздел, предмет, изменения без секретов и
шума с обрезанным длинным текстом, примечание, адрес.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import pytest

from .pg_admin import PYTHON, АДРЕС, sql, нужна_база, свежая_база

pytestmark = нужна_база

ОКРУЖЕНИЕ = {
    **os.environ,
    "DB_CONNECTION": "pgsql",
    "DB_URL": АДРЕС,
    "DJANGO_DATABASE_URL": АДРЕС,
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "QUEUE_CONNECTION": "sync",
}

СТОЛБЦЫ = (
    "user_id, user_name, user_role, action, section, subject_type, subject_id, "
    "subject_label, changes, note, ip"
)

#: Запись в отдельном процессе Django, как на сервере
ПРОБА = """
import json, sys
import django
django.setup()
from django.db import connection
from savdex import access, audit

a = json.loads(sys.argv[1])
actor = None
if a["actor"]:
    actor = access.Admin(id=a["actor"]["id"], name=a["actor"]["name"], email="x",
                         is_admin=True, role=a["actor"]["role"], status="active")
audit.record(connection, action=a["action"], section=a["section"], actor=actor,
             subject_type=a["subject_type"], subject_id=a["subject_id"],
             subject_label=a["subject_label"], changes=a["changes"], note=a["note"],
             ip="127.0.0.1")
"""

ИМЯ = "Журнальный " + "Ж" * 130
COUNTRY = "App\\Models\\Country"


@pytest.fixture(scope="module")
def данные() -> dict[str, Any]:
    свежая_база()

    [(uid,)] = sql(
        "insert into users (name, email, password, is_admin, admin_role, created_at, updated_at) "
        "values (%s, 'j@savdex.uz', 'x', true, 'content_manager', now(), now()) returning id",
        [ИМЯ],
    )
    [(cid,)] = sql(
        "insert into countries (code, phone_code, currency_code, created_at, updated_at) "
        "values ('zz', '+0', 'ZZZ', now(), now()) returning id"
    )

    return {"uid": uid, "cid": cid}


def _python(запись: dict[str, Any], данные: dict[str, Any]) -> None:
    from savdex import audit

    python = {
        "action": запись["action"],
        "section": запись["section"],
        "actor": (
            {"id": данные["uid"], "name": ИМЯ, "role": "content_manager"}
            if запись["actor_id"]
            else None
        ),
        "subject_type": COUNTRY if запись["subject_id"] else None,
        "subject_id": запись["subject_id"],
        "subject_label": audit.label({"code": "zz"}, "Country", запись["subject_id"])
        if запись["subject_id"]
        else None,
        "changes": запись.get("changes") or {},
        "note": запись.get("note"),
    }

    subprocess.run(
        [sys.executable, "-c", ПРОБА, json.dumps(python)],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
        check=True,
    )


def _последняя() -> tuple[Any, ...]:
    [row] = sql(f"select {СТОЛБЦЫ} from admin_actions order by id desc limit 1")

    return row


СЛУЧАИ = {
    "правка с секретами, шумом и длинным текстом": {
        "action": "updated",
        "section": "catalogs",
        "changes": {
            "before": {"phone_code": "+1", "password": "старый", "updated_at": "2026-01-01"},
            "after": {
                "phone_code": "+998",
                "password": "новый",
                "remember_token": "t",
                "updated_at": "2026-02-02",
                "search_text": "x",
                "note": "Д" * 400,
                "is_active": False,
                "sort": 3,
                "empty": "",
                "nothing": None,
                "nested": {"ru": "Узбекистан"},
            },
        },
        "note": "Переименовал «страну» — проверка",
        # Секреты — «···», шум (updated_at, search_text) убран, длинное
        # обрезано до 300 знаков с «…»; пустое и null — как есть
        "ожидаемые": {
            "before": {"phone_code": "+1", "password": "···"},
            "after": {
                "phone_code": "+998",
                "password": "···",
                "remember_token": "···",
                "note": "Д" * 300 + "…",
                "is_active": False,
                "sort": 3,
                "empty": "",
                "nothing": None,
                "nested": {"ru": "Узбекистан"},
            },
        },
    },
    "создание без изменений": {"action": "created", "section": "catalogs"},
    "из консоли, без автора": {"action": "deleted", "section": "catalogs", "no_actor": True},
    "без предмета": {"action": "exported", "section": "backups", "no_subject": True},
}


@pytest.mark.parametrize("случай", list(СЛУЧАИ))
def test_строка_журнала(данные, случай):
    описание = СЛУЧАИ[случай]
    запись = {
        "action": описание["action"],
        "section": описание["section"],
        "changes": описание.get("changes", {}),
        "note": описание.get("note"),
        "actor_id": None if описание.get("no_actor") else данные["uid"],
        "subject_id": None if описание.get("no_subject") else данные["cid"],
    }

    _python(запись, данные)
    строка = _последняя()

    автор = (
        (None, "консоль", None)
        if описание.get("no_actor")
        else (данные["uid"], ИМЯ[:120], "content_manager")
    )
    предмет = (None, None, None) if описание.get("no_subject") else (COUNTRY, данные["cid"], "zz")
    assert строка == (
        *автор,
        описание["action"],
        описание["section"],
        *предмет,
        описание.get("ожидаемые"),
        описание.get("note"),
        "127.0.0.1",
    )
