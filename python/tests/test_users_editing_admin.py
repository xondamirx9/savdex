"""
Пользователи на Django, этап 6: заведение, правка и действия вместо
Filament (удаление в два шага — tests/test_users_admin.py).

- новый: пароль генерируется и показывается один раз, в базе — bcrypt
  $2y$, смена при входе; почта строчными и уникальна среди действующих;
- роль и личные права правит только тот, у кого roles.edit;
- «Подтвердить почту»: событие компании и уведомление человеку;
- «Выдать пароль»: смена при входе обязательна; «Заблокировать» — не себя;
- чужую учётку сотрудника (почта, пароль, статус) — только с roles.edit;
- выгрузка — право users.export.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/accounts/user/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "support")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from activity_events")
    sql("delete from users where email like 'client%%'")
    sql("delete from companies")
    sql("delete from admin_actions where section = 'users'")


def _форма(**поля: str) -> dict[str, Any]:
    return {
        "name": "Иван Клиентов",
        "email": "Client@Example.com",
        "phone": "",
        "locale": "ru",
        "company_id": "",
        "company_role": "owner",
        "status": "active",
        "password": "Abc12345xyz",
        "must_change_password": "on",
        **поля,
    }


def _клиент(**поля: Any) -> int:
    строка = {"name": "Клиент", "email": "client@example.com", "status": "active", **поля}
    columns = list(строка)
    [(pk,)] = sql(
        f"insert into users ({', '.join(columns)}, password, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, 'x', now(), now()) returning id",
        list(строка.values()),
    )

    return int(pk)


def test_новый_пользователь(люди):
    _, ответ = django(люди["admin"], ("post", LIST + "add/", _форма()))

    assert ответ["status"] == 302, ответ["body"][:2000]
    [(email, password, must, is_admin)] = sql(
        "select email, password, must_change_password, is_admin from users "
        "where email like 'client%%'"
    )
    assert email == "client@example.com"
    assert password.startswith("$2y$") and must is True and is_admin is False
    assert журнал("created")["section"] == "users"


def test_почта_уникальна_среди_действующих(люди):
    _клиент()
    _клиент(email="client-old@example.com", deleted_at="2026-01-01")

    _, занята, свободна = django(
        люди["admin"],
        ("post", LIST + "add/", _форма(email="CLIENT@example.com")),
        ("post", LIST + "add/", _форма(email="client-old@example.com")),
    )

    assert занята["status"] == 200 and "Такая почта уже занята" in занята["body"]
    assert свободна["status"] == 302, "адрес отключённого аккаунта свободен"


def test_роль_правит_только_суперадмин(люди):
    pk = _клиент()

    _, админ = django(
        люди["admin"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма(email="client@example.com", is_admin="on", admin_role="superadmin"),
        ),
    )
    assert админ["status"] == 302
    assert sql("select is_admin, admin_role from users where id = %s", [pk]) == [(False, None)]

    _, суперадмин = django(
        люди["superadmin"],
        (
            "post",
            f"{LIST}{pk}/change/",
            {
                **_форма(email="client@example.com"),
                "is_admin": "on",
                "admin_role": "moderator",
                "grant": ["payments.view"],
                "revoke": [],
            },
        ),
    )
    assert суперадмин["status"] == 302, суперадмин["body"][:2000]
    [(is_admin, role, permissions)] = sql(
        "select is_admin, admin_role, admin_permissions from users where id = %s", [pk]
    )
    assert (is_admin, role) == (True, "moderator")
    assert permissions == {"grant": ["payments.view"], "revoke": []}


def test_подтвердить_почту(люди):
    [(company,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values ('Стройбаза', 'stroybaza', 'active', now(), now()) returning id"
    )
    pk = _клиент(company_id=company)

    _, ответ = django(люди["admin"], ("post", f"{LIST}{pk}/act/", {"act": "verify"}))

    assert ответ["status"] == 302
    assert sql("select email_verified_at is not null from users where id = %s", [pk]) == [(True,)]
    assert sql("select message from activity_events") == [
        ("Почта client@example.com подтверждена администратором",)
    ]
    assert sql("select type, title from user_notifications where user_id = %s", [pk]) == [
        ("system", "Почта подтверждена")
    ]


def test_выдать_пароль_и_заблокировать(люди):
    pk = _клиент()

    _, пароль, блок = django(
        люди["admin"],
        ("post", f"{LIST}{pk}/act/", {"act": "password"}),
        ("post", f"{LIST}{pk}/act/", {"act": "status"}),
    )
    _, себя = django(люди["admin"], ("post", f"{LIST}{люди['admin']}/act/", {"act": "status"}))

    assert пароль["status"] == 302 and блок["status"] == 302
    [(password, must, status)] = sql(
        "select password, must_change_password, status from users where id = %s", [pk]
    )
    assert password.startswith("$2y$") and must is True and status == "blocked"
    assert себя["status"] == 403
    # Как AuditObserver::name: блокировка ищется отбором по действию
    assert журнал("blocked")["section"] == "users"
    assert "password" not in str(журнал("blocked")["changes"])


def test_учётку_сотрудника_бережёт_roles_edit(люди):
    """
    Администратор без roles.edit не выдаёт суперадмину пароль, не меняет
    ему почту и не блокирует: иначе вошёл бы под ним. Имя — можно.
    """
    суперадмин = люди["superadmin"]
    [(hash_before,)] = sql("select password from users where id = %s", [суперадмин])

    _, пароль, блок, правка = django(
        люди["admin"],
        ("post", f"{LIST}{суперадмин}/act/", {"act": "password"}),
        ("post", f"{LIST}{суперадмин}/act/", {"act": "status"}),
        (
            "post",
            f"{LIST}{суперадмин}/change/",
            {
                **_форма(email="evil@example.com", status="blocked"),
                "name": "Сотрудник superadmin",
            },
        ),
    )
    _, страница = django(люди["admin"], ("get", f"{LIST}{суперадмин}/change/", None))

    assert пароль["status"] == 403 and блок["status"] == 403
    assert правка["status"] == 302, правка["body"][:2000]
    assert sql("select password, email, status from users where id = %s", [суперадмин]) == [
        (hash_before, "superadmin@savdex.uz", "active")
    ]
    assert "Выдать пароль" not in страница["body"]
    assert 'name="email"' not in страница["body"]

    # Суперадмину (roles.edit) можно — отдельному сотруднику: выданный
    # пароль требует смены при входе, а люди модуля нужны дальше
    модератор = сотрудник("moderator")
    _, свой = django(суперадмин, ("post", f"{LIST}{модератор}/act/", {"act": "password"}))
    assert свой["status"] == 302
    assert sql("select must_change_password from users where id = %s", [модератор]) == [(True,)]
    sql("delete from users where id = %s", [модератор])


def test_поддержка_смотрит_выгрузка_по_праву(люди):
    pk = _клиент()

    _, список, правка = django(
        люди["support"],
        ("get", LIST, None),
        ("post", f"{LIST}{pk}/change/", _форма(email="client@example.com", name="Взлом")),
    )
    _, выгрузка = django(люди["admin"], ("get", LIST + "export/?format=csv", None))
    _, без_права = django(люди["support"], ("get", LIST + "export/", None))

    assert список["status"] == 200
    assert правка["status"] == 403
    assert "Имя,Почта,Телефон" in выгрузка["body"] and "client@example.com" in выгрузка["body"]
    assert без_права["status"] == 403
