"""
CRM на Django, этап 6: раздел «Контакты» вместо Filament.

- список: имя с должностью, компания, число лидов и сделок (удалённые
  не считаются), поиск по имени, почте и компании, отбор «Без компании»;
- создание: кто завёл (created_by), пустые поля — NULL, строка журнала;
- правка — строка журнала «изменено»; неверная почта не сохраняется;
- удаление — в корзину (deleted_at и updated_at), только суперадмин;
- права: продажи правят, поддержка только смотрит, модератор не видит.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/crm/contact/"
ADD = LIST + "add/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "sales", "support", "moderator")}


def _компания(name: str) -> int:
    [(pk,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values (%s, %s, 'active', now(), now()) returning id",
        [name, name.lower().replace(" ", "-")],
    )

    return int(pk)


def _контакт(name: str, **поля: Any) -> int:
    columns = ["name", *поля]
    [(pk,)] = sql(
        f"insert into crm_contacts ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [name, *поля.values()],
    )

    return int(pk)


def _лид(contact_id: int, *, удалён: bool = False) -> None:
    sql(
        "insert into crm_leads (title, contact_id, created_at, updated_at, deleted_at) "
        "values ('Лид', %s, now(), now(), " + ("now()" if удалён else "null") + ")",
        [contact_id],
    )


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from crm_leads")
    sql("delete from crm_deals")
    sql("delete from crm_contacts")
    sql("delete from companies")
    sql("delete from admin_actions where section = 'contacts'")


def test_список_поиск_и_счётчики(люди):
    company = _компания("Стройбаза")
    иван = _контакт("Иван Петров", position="закупщик", company_id=company, email="ivan@x.uz")
    _контакт("Ольга Сидорова", email="olga@y.uz")
    _лид(иван)
    _лид(иван, удалён=True)

    _, все, поиск, без_компании = django(
        люди["sales"],
        ("get", LIST, None),
        ("get", LIST + "?q=ivan@x", None),
        ("get", LIST + "?company=none", None),
    )

    assert все["status"] == 200
    assert "Иван Петров, закупщик" in все["body"] and "Стройбаза" in все["body"]
    # Один живой лид, удалённый не считается
    assert '<td class="field-leads">1</td>' in все["body"]
    assert "Ольга" not in поиск["body"] and "Иван Петров" in поиск["body"]
    assert "Ольга" in без_компании["body"] and "Иван Петров" not in без_компании["body"]


def test_создание_кто_завёл_и_журнал(люди):
    company = _компания("Стройбаза")

    _, ответ = django(
        люди["sales"],
        (
            "post",
            ADD,
            {
                "name": "Иван Петров",
                "position": "",
                "company": str(company),
                "phone": "+998 90 123 45 67",
                "email": "",
                "telegram": "",
                "note": "",
            },
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:2000]
    assert sql(
        "select name, position, company_id, phone, email, telegram, note, created_by "
        "from crm_contacts"
    ) == [("Иван Петров", None, company, "+998 90 123 45 67", None, None, None, люди["sales"])]
    строка = журнал("created")
    assert (строка["section"], строка["subject_type"], строка["subject_label"]) == (
        "contacts",
        "App\\Models\\Crm\\Contact",
        "Иван Петров",
    )


def test_правка_и_неверная_почта(люди):
    pk = _контакт("Иван Петров", phone="1")

    _, плохо, хорошо = django(
        люди["sales"],
        ("post", f"{LIST}{pk}/change/", {"name": "Иван Петров", "email": "не-почта"}),
        ("post", f"{LIST}{pk}/change/", {"name": "Иван Петров", "phone": "2"}),
    )

    assert плохо["status"] == 200
    assert хорошо["status"] == 302
    assert sql("select phone, email from crm_contacts where id = %s", [pk]) == [("2", None)]
    assert журнал("updated")["changes"]["after"] == {"phone": "2"}


def test_удаление_в_корзину_только_суперадмин(люди):
    pk = _контакт("Иван Петров")

    _, продажи = django(люди["sales"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))
    assert продажи["status"] == 403
    assert sql("select deleted_at is null from crm_contacts where id = %s", [pk]) == [(True,)]

    _, удалено, список = django(
        люди["superadmin"],
        ("post", f"{LIST}{pk}/delete/", {"post": "yes"}),
        ("get", LIST, None),
    )

    assert удалено["status"] == 302
    assert sql(
        "select deleted_at is not null, deleted_at = updated_at from crm_contacts where id = %s",
        [pk],
    ) == [(True, True)]
    assert "field-person" not in список["body"], "удалённый в списке не виден"
    assert журнал("deleted")["subject_label"] == "Иван Петров"


def test_поддержка_смотрит_модератор_не_видит(люди):
    pk = _контакт("Иван Петров")

    _, список, создание, правка = django(
        люди["support"],
        ("get", LIST, None),
        ("get", ADD, None),
        ("post", f"{LIST}{pk}/change/", {"name": "Другое имя"}),
    )

    assert список["status"] == 200 and "Иван Петров" in список["body"]
    assert создание["status"] == 403
    assert правка["status"] == 403
    assert sql("select name from crm_contacts where id = %s", [pk]) == [("Иван Петров",)]

    _, модератор = django(люди["moderator"], ("get", LIST, None))
    assert модератор["status"] == 403
