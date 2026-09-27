"""
Журнал действий: строка от Python против строки от PHP.

Одни и те же записи делаются через AdminLog::record (PHP,
tests/fixtures/audit_record.php) и через savdex.audit.record (Python),
и строки в admin_actions обязаны совпасть: автор, роль, действие,
раздел, предмет, изменения без секретов и шума, примечание, адрес.

Нужны PHP с зависимостями и PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

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

pytestmark = pytest.mark.skipif(
    not АДРЕС,
    reason="нет SAVDEX_PARITY_PG_URL — сравнение требует PHP и PostgreSQL",
)

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

#: Python-запись в отдельном процессе Django, как на сервере
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


def _sql(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    import psycopg

    with psycopg.connect(АДРЕС, autocommit=True) as соединение:
        курсор = соединение.execute(query, params or [])

        return курсор.fetchall() if курсор.description else []


@pytest.fixture(scope="module")
def данные() -> dict[str, Any]:
    if "test" not in urlparse(АДРЕС).path:
        pytest.fail("SAVDEX_PARITY_PG_URL ведёт в базу без «test» в имени — отказываюсь стирать")

    subprocess.run(
        ["php", "artisan", "migrate:fresh", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        capture_output=True,
        check=True,
    )

    [(uid,)] = _sql(
        "insert into users (name, email, password, is_admin, admin_role, created_at, updated_at) "
        "values (%s, 'j@savdex.uz', 'x', true, 'content_manager', now(), now()) returning id",
        ["Журнальный " + "Ж" * 130],
    )
    [(cid,)] = _sql(
        "insert into countries (code, phone_code, currency_code, created_at, updated_at) "
        "values ('zz', '+0', 'ZZZ', now(), now()) returning id"
    )

    return {"uid": uid, "cid": cid}


def _php(запись: dict[str, Any]) -> None:
    subprocess.run(
        ["php", "python/tests/fixtures/audit_record.php"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        input=json.dumps(запись),
        capture_output=True,
        text=True,
        check=True,
    )


def _python(запись: dict[str, Any], данные: dict[str, Any]) -> None:
    from savdex import audit

    python = {
        "action": запись["action"],
        "section": запись["section"],
        "actor": (
            {"id": данные["uid"], "name": "Журнальный " + "Ж" * 130, "role": "content_manager"}
            if запись["actor_id"]
            else None
        ),
        "subject_type": "App\\\\Models\\\\Country".replace("\\\\", "\\")
        if запись["subject_id"]
        else None,
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
    [row] = _sql(f"select {СТОЛБЦЫ} from admin_actions order by id desc limit 1")

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
    },
    "создание без изменений": {"action": "created", "section": "catalogs"},
    "из консоли, без автора": {"action": "deleted", "section": "catalogs", "no_actor": True},
    "без предмета": {"action": "exported", "section": "backups", "no_subject": True},
}


@pytest.mark.parametrize("случай", list(СЛУЧАИ))
def test_строки_журнала_совпадают(данные, случай):
    описание = СЛУЧАИ[случай]
    запись = {
        "action": описание["action"],
        "section": описание["section"],
        "changes": описание.get("changes", {}),
        "note": описание.get("note"),
        "actor_id": None if описание.get("no_actor") else данные["uid"],
        "subject_id": None if описание.get("no_subject") else данные["cid"],
    }

    _php(запись)
    php = _последняя()

    _python(запись, данные)
    python = _последняя()

    assert python == php
