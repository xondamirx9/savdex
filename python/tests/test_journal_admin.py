"""
Журнал действий на Django, этап 6: раздел вместо Filament, только чтение.

- видят суперадмин, администратор и финансы; продажи — нет;
- свежее сверху, роль на момент действия, отборы по разделу, действию,
  сотруднику и «за сегодня», поиск;
- «что изменилось»: поле, было, стало — как AdminLog::readable;
- ни создать, ни изменить, ни удалить.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/journal/adminaction/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "finance", "sales")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from admin_actions")


def _запись(**поля: Any) -> int:
    строка = {
        "user_name": "Сотрудник admin",
        "user_role": "admin",
        "action": "updated",
        "section": "companies",
        "created_at": "now()",
        **поля,
    }
    if isinstance(строка.get("changes"), dict):
        строка["changes"] = json.dumps(строка["changes"], ensure_ascii=False)
    columns = list(строка)
    values = ["now()" if v == "now()" else "%s" for v in строка.values()]
    [(pk,)] = sql(
        f"insert into admin_actions ({', '.join(columns)}) values ({', '.join(values)}) "
        "returning id",
        [v for v in строка.values() if v != "now()"],
    )

    return int(pk)


def test_кто_видит(люди):
    _запись(subject_label="Стройбаза")

    _, админ = django(люди["admin"], ("get", LIST, None))
    _, финансы = django(люди["finance"], ("get", LIST, None))
    _, продажи = django(люди["sales"], ("get", LIST, None))

    assert админ["status"] == 200 and "Стройбаза" in админ["body"]
    assert финансы["status"] == 200
    assert продажи["status"] == 403


def test_список_и_отборы(люди):
    _запись(subject_label="Стройбаза", section="companies", action="blocked", user_id=люди["admin"])
    _запись(
        subject_label="Цемент",
        section="listings",
        action="approved",
        user_name="Модератор",
        user_role="moderator",
        created_at="2020-01-01 10:00:00",
    )

    _, все, раздел, поиск, сегодня, сотрудник_ = django(
        люди["admin"],
        ("get", LIST, None),
        ("get", LIST + "?section=listings", None),
        ("get", LIST + "?q=Строй", None),
        ("get", LIST + "?today=1", None),
        ("get", LIST + f"?user={люди['admin']}", None),
    )

    assert все["body"].index("Стройбаза") < все["body"].index("Цемент"), "свежее сверху"
    assert "Блокировка" in все["body"] and "Модератор" in все["body"]
    assert "Объявления и товары" in все["body"]
    assert "Цемент" in раздел["body"] and "Стройбаза" not in раздел["body"]
    assert "Стройбаза" in поиск["body"] and "Цемент" not in поиск["body"]
    assert "Стройбаза" in сегодня["body"] and "Цемент" not in сегодня["body"]
    assert "Стройбаза" in сотрудник_["body"] and "Цемент" not in сотрудник_["body"]


def test_что_изменилось(люди):
    pk = _запись(
        subject_label="Стройбаза",
        changes={
            "before": {"status": "active", "note": None, "is_verified": False, "url": ""},
            "after": {
                "status": "blocked",
                "note": "спам",
                "is_verified": True,
                "url": "",
                "tags": ["a/b"],
            },
        },
    )

    _, страница = django(люди["admin"], ("get", f"{LIST}{pk}/change/", None))

    body = страница["body"]
    assert страница["status"] == 200
    assert "<td><code>status</code></td><td>active</td><td><b>blocked</b></td>" in body
    assert "<td><code>note</code></td><td>—</td><td><b>спам</b></td>" in body
    assert "<td><code>is_verified</code></td><td>нет</td><td><b>да</b></td>" in body
    assert "(пусто)" in body
    assert "[&quot;a\\/b&quot;]" in body, "массив — JSON, как json_encode"


def test_только_чтение(люди):
    pk = _запись(subject_label="Стройбаза")

    _, создать, удалить, править = django(
        люди["superadmin"],
        ("get", LIST + "add/", None),
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
        ("post", f"{LIST}{pk}/change/", {"user_name": "Подчищено"}),
    )

    assert создать["status"] == 403
    assert удалить["status"] == 403
    assert править["status"] == 403
    assert sql("select user_name from admin_actions") == [("Сотрудник admin",)]
