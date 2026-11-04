"""
Мегаадмин и защита суперадминов (Ж7) — оба раздела: «Роли и права» и
форма «Пользователи».

- суперадмин не снижает другого суперадмина, не трогает его учётку
  (пароль, блокировка) и не назначает суперадмина или мегаадмина;
- мегаадмин назначает и снимает суперадмина, но мегаадмина в панели не
  назначит никто: только командой manage.py admin;
- учётку мегаадмина в панели не меняет никто, кроме него самого;
- роль и права, выданные формой «Пользователи», — строкой раздела
  «Роли и права» в журнале.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from savdex.accounts import hierarchy

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

ROLES = "/py/admin/accounts/staffmember/"
USERS = "/py/admin/accounts/user/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("megaadmin", "superadmin")}


@pytest.fixture(autouse=True)
def чисто(люди) -> None:
    sql("delete from users where email like 'client%%'")
    sql("delete from admin_actions where section in ('roles', 'users')")
    sql(
        "update users set is_admin = true, admin_role = split_part(email, '@', 1), "
        "status = 'active', admin_permissions = null where email like '%%@savdex.uz'"
    )


def _клиент(email: str = "client@example.com", **поля: Any) -> int:
    строка = {"name": "Клиент", "email": email, "status": "active", **поля}
    columns = list(строка)
    [(pk,)] = sql(
        f"insert into users ({', '.join(columns)}, password, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, 'x', now(), now()) returning id",
        list(строка.values()),
    )

    return int(pk)


def _роль(pk: int) -> tuple[bool, str | None, str]:
    [row] = sql("select is_admin, admin_role, status from users where id = %s", [pk])

    return row


def _форма(email: str, **поля: str) -> dict[str, str]:
    return {
        "name": "Клиент",
        "email": email,
        "phone": "",
        "locale": "ru",
        "company_id": "",
        "company_role": "owner",
        "status": "active",
        **поля,
    }


def test_суперадмин_не_трогает_другого_суперадмина(люди):
    второй = _клиент(is_admin=True, admin_role="superadmin")

    _, понизить, отключить, пароль, блок, форма, отключить_акк = django(
        люди["superadmin"],
        ("post", f"{ROLES}{второй}/act/", {"act": "role", "admin_role": "admin"}),
        ("post", f"{ROLES}{второй}/act/", {"act": "access"}),
        ("post", f"{USERS}{второй}/act/", {"act": "password"}),
        ("post", f"{USERS}{второй}/act/", {"act": "status"}),
        (
            "post",
            f"{USERS}{второй}/change/",
            _форма("client@example.com", is_admin="on", admin_role="admin"),
        ),
        (
            "post",
            USERS,
            {"action": "disable", "_selected_action": [str(второй)], "post": "yes"},
        ),
    )

    assert [понизить["status"], отключить["status"], пароль["status"], блок["status"]] == [302] * 4
    assert форма["status"] == 200 and hierarchy.SUPER_BY_MEGA in форма["body"]
    assert отключить_акк["status"] in (200, 302)
    assert _роль(второй) == (True, "superadmin", "active")
    assert sql("select password, deleted_at from users where id = %s", [второй]) == [("x", None)]


@pytest.mark.parametrize("раздел", ["roles", "users"])
def test_суперадмина_назначает_только_мегаадмин(люди, раздел):
    клиент = _клиент(is_admin=True, admin_role="admin")

    def повысить(uid: int) -> dict[str, Any]:
        шаг = (
            ("post", f"{ROLES}{клиент}/act/", {"act": "role", "admin_role": "superadmin"})
            if раздел == "roles"
            else (
                "post",
                f"{USERS}{клиент}/change/",
                _форма("client@example.com", is_admin="on", admin_role="superadmin"),
            )
        )
        _, ответ = django(uid, шаг)

        return ответ

    повысить(люди["superadmin"])
    assert _роль(клиент)[1] == "admin"

    ответ = повысить(люди["megaadmin"])
    assert ответ["status"] == 302, ответ["body"][:2000]
    assert _роль(клиент)[1] == "superadmin"
    assert журнал("granted")["section"] == "roles"
    assert журнал("granted")["changes"]["after"]["admin_role"] == "superadmin"


def test_мегаадмин_снижает_суперадмина(люди):
    второй = _клиент(is_admin=True, admin_role="superadmin")

    django(
        люди["megaadmin"],
        ("post", f"{ROLES}{второй}/act/", {"act": "role", "admin_role": "admin"}),
    )
    assert _роль(второй)[1] == "admin"


def test_мегаадмина_в_панели_не_назначить_и_не_снять(люди):
    клиент = _клиент(is_admin=True, admin_role="superadmin")
    второй = _клиент("client-mega@example.com", is_admin=True, admin_role="megaadmin")

    _, *ответы = django(
        люди["megaadmin"],
        ("post", f"{ROLES}{клиент}/act/", {"act": "role", "admin_role": "megaadmin"}),
        (
            "post",
            f"{USERS}{клиент}/change/",
            _форма("client@example.com", is_admin="on", admin_role="megaadmin"),
        ),
        ("post", f"{ROLES}{второй}/act/", {"act": "role", "admin_role": "admin"}),
        ("post", f"{ROLES}{второй}/act/", {"act": "access"}),
        ("post", f"{USERS}{второй}/act/", {"act": "status"}),
        ("post", f"{USERS}{второй}/act/", {"act": "password"}),
    )

    assert hierarchy.MEGA_ONLY_CLI in ответы[1]["body"]
    assert _роль(клиент) == (True, "superadmin", "active")
    assert _роль(второй) == (True, "megaadmin", "active")
    assert sql("select password from users where id = %s", [второй]) == [("x",)]


def test_выдачу_роли_формой_видно_в_журнале_ролей(люди):
    клиент = _клиент()

    _, ответ = django(
        люди["superadmin"],
        (
            "post",
            f"{USERS}{клиент}/change/",
            {
                **_форма("client@example.com", is_admin="on", admin_role="moderator"),
                "grant": ["payments.view"],
                "revoke": [],
            },
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:2000]
    строка = журнал("granted")
    assert строка["section"] == "roles"
    assert строка["changes"]["after"] == {
        "доступ в панель": "есть",
        "admin_role": "moderator",
        "права": "выдано: payments.view",
    }


def test_правило_целиком():
    """Без базы: кто кого может, по ступеням."""
    from savdex import access
    from savdex.accounts.models import User

    def кто(role: str) -> access.Admin:
        return access.Admin(id=1, name="", email="", is_admin=True, role=role, status="active")

    def кого(role: str | None, pk: int = 2) -> User:
        return User(pk=pk, is_admin=role is not None, admin_role=role, status="active")

    мега, супер, админ = кто("megaadmin"), кто("superadmin"), кто("admin")

    # Назначить суперадмина — только мегаадмин
    assert hierarchy.refusal(супер, кого("admin"), {"admin_role": "superadmin"})
    assert hierarchy.refusal(админ, кого("admin"), {"admin_role": "superadmin"})
    # Мегаадмина не назначает никто
    assert hierarchy.refusal(мега, кого("superadmin"), {"admin_role": "megaadmin"})
    assert hierarchy.refusal(мега, кого(None), {"is_admin": True, "admin_role": "megaadmin"})
    # Обычные роли — как раньше
    assert hierarchy.refusal(админ, кого("sales"), {"admin_role": "moderator"}) is None
    assert hierarchy.refusal(супер, кого("sales"), {"status": "blocked"}) is None
    # Себе суперадмин имя и пароль менять может
    assert hierarchy.refusal(супер, кого("superadmin", pk=1), {"password": True}) is None
