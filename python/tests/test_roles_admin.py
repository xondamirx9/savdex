"""
«Роли и права» на Django, этап 6: вместо страницы Filament Roles.

- раздел — только с правами roles (у суперадмина); список — сотрудники;
- «Выдать доступ» существующему пользователю, с ролью;
- «Роль» и «Личные права» (поверх роли, только из списка выдаваемых);
- «Отключить доступ»: роль и личные права сохраняются;
- последнего суперадмина нельзя ни понизить, ни отключить;
- журнал: «изменено» раздела «Пользователи» (AuditObserver у User) и
  строка «Выдача прав» / «Отзыв прав».

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/accounts/staffmember/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator")}


@pytest.fixture(autouse=True)
def чисто(люди) -> None:
    sql("delete from users where email like 'client%%'")
    sql("delete from admin_actions where section in ('roles', 'users')")
    sql(
        "update users set is_admin = true, admin_role = split_part(email, '@', 1), "
        "admin_permissions = null where email like '%%@savdex.uz'"
    )


def _клиент(**поля: Any) -> int:
    строка = {"name": "Клиент", "email": "client@example.com", "status": "active", **поля}
    columns = list(строка)
    [(pk,)] = sql(
        f"insert into users ({', '.join(columns)}, password, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, 'x', now(), now()) returning id",
        list(строка.values()),
    )

    return int(pk)


def _act(uid: int, pk: int, **данные: Any) -> dict[str, Any]:
    _, ответ = django(uid, ("post", f"{LIST}{pk}/act/", данные))

    return ответ


def _журнал(section: str) -> list[tuple[Any, ...]]:
    return sql(
        "select action, subject_id, changes::text, note from admin_actions "
        "where section = %s order by id",
        [section],
    )


def test_раздел_только_у_суперадмина(люди):
    _клиент()

    _, список, страница = django(
        люди["superadmin"],
        ("get", LIST, None),
        ("get", f"{LIST}{люди['moderator']}/change/", None),
    )
    _, админ = django(люди["admin"], ("get", LIST, None))

    assert список["status"] == 200
    assert "moderator@savdex.uz" in список["body"]
    assert "client@example.com" not in список["body"], "в списке только сотрудники"
    assert "Выдать доступ" in список["body"]
    assert страница["status"] == 200 and "Что доступно" in страница["body"]
    assert админ["status"] == 403


def test_выдать_доступ(люди):
    pk = _клиент()

    _, нет_такого, выдано = django(
        люди["superadmin"],
        ("post", LIST + "grant/", {"email": "nobody@example.com", "admin_role": "moderator"}),
        ("post", LIST + "grant/", {"email": "CLIENT@example.com", "admin_role": "moderator"}),
    )

    assert "Такого пользователя нет" in нет_такого["body"]
    assert выдано["status"] == 302
    assert sql("select is_admin, admin_role from users where id = %s", [pk]) == [
        (True, "moderator")
    ]
    [(action, subject, _, note)] = _журнал("roles")
    assert (action, subject, note) == ("granted", pk, "Выдан доступ в панель: Модератор")
    [(action, subject, changes, _)] = _журнал("users")
    assert (action, subject) == ("updated", pk)
    assert json.loads(changes)["after"] == {"is_admin": True, "admin_role": "moderator"}


def test_роль_и_личные_права(люди):
    pk = люди["moderator"]

    _act(люди["superadmin"], pk, act="role", admin_role="support")
    _act(
        люди["superadmin"],
        pk,
        act="rights",
        grant=["payments.view", "не.право"],
        revoke=["reviews.edit"],
    )

    [(role, permissions)] = sql(
        "select admin_role, admin_permissions from users where id = %s", [pk]
    )
    assert role == "support"
    assert permissions == {"grant": ["payments.view"], "revoke": ["reviews.edit"]}

    роли = _журнал("roles")
    assert [json.loads(changes) for _, _, changes, _ in роли] == [
        {"before": {"admin_role": "moderator"}, "after": {"admin_role": "support"}},
        {
            "before": {"права": "нет"},
            "after": {"права": "выдано: payments.view; отозвано: reviews.edit"},
        },
    ]
    assert [action for action, *_ in _журнал("users")] == ["updated", "updated"]


def test_отключить_доступ(люди):
    pk = люди["admin"]
    sql(
        "update users set admin_permissions = %s where id = %s",
        [json.dumps({"grant": ["payments.view"], "revoke": []}), pk],
    )

    ответ = _act(люди["superadmin"], pk, act="access")

    assert ответ["status"] == 302
    assert sql("select is_admin, admin_role, admin_permissions from users where id = %s", [pk]) == [
        (False, "admin", {"grant": ["payments.view"], "revoke": []})
    ], "роль и личные права сохраняются"
    assert журнал("revoked")["section"] == "roles"


def test_последний_суперадмин(люди):
    pk = люди["superadmin"]

    _, понизить, отключить = django(
        pk,
        ("post", f"{LIST}{pk}/act/", {"act": "role", "admin_role": "admin"}),
        ("post", f"{LIST}{pk}/act/", {"act": "access"}),
    )

    assert понизить["status"] == 302 and отключить["status"] == 302
    assert sql("select is_admin, admin_role from users where id = %s", [pk]) == [
        (True, "superadmin")
    ]
    assert _журнал("roles") == []

    # Второй суперадмин есть — теперь можно
    второй = _клиент(is_admin=True, admin_role="superadmin")
    _act(pk, второй, act="role", admin_role="admin")
    assert sql("select admin_role from users where id = %s", [второй]) == [("admin",)]


def test_без_прав_раздела_нельзя(люди):
    pk = люди["moderator"]

    ответы = [
        _act(люди["admin"], pk, act="role", admin_role="superadmin"),
        _act(люди["admin"], pk, act="access"),
    ]
    _, выдача = django(
        люди["admin"],
        ("post", LIST + "grant/", {"email": "moderator@savdex.uz", "admin_role": "superadmin"}),
    )

    клиент = _клиент()
    ответы.append(_act(люди["superadmin"], клиент, act="rights", grant=["payments.view"]))

    assert [ответ["status"] for ответ in ответы] == [403, 403, 403]
    assert sql("select admin_permissions from users where id = %s", [клиент]) == [(None,)]
    assert выдача["status"] == 403
    assert sql("select is_admin, admin_role from users where id = %s", [pk]) == [
        (True, "moderator")
    ]
