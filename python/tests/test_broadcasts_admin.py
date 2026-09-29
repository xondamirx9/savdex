"""
Рассылки на Django, этап 6: раздел вместо Filament.

- черновик: заведение и правка, у «на тарифе» тариф обязателен;
- охват сегмента виден до отправки; «Отправить» — уведомление каждому
  действующему получателю сегмента, автор, число и время у рассылки;
- отправленная не правится и не отправляется второй раз;
- контент-менеджер смотрит, но не заводит; удаление — суперадмин.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/system/broadcast/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "content_manager")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from user_notifications")
    sql("delete from broadcasts")
    sql("delete from users where email like 'client-%%'")
    sql("delete from companies")
    sql("delete from admin_actions where section = 'broadcasts'")


def _клиенты() -> None:
    [(checked,)] = sql(
        "insert into companies (name, slug, status, verification_level, created_at, updated_at) "
        "values ('Проверенная', 'checked', 'active', 2, now(), now()) returning id"
    )
    for i, (company, status) in enumerate(
        [(checked, "active"), (None, "active"), (None, "blocked")]
    ):
        sql(
            "insert into users (name, email, password, company_id, status, created_at, "
            "updated_at) values (%s, %s, 'x', %s, %s, now(), now())",
            [f"Клиент {i}", f"client-{i}@example.com", company, status],
        )


def _форма(**поля: str) -> dict[str, str]:
    return {
        "title": "Оплата через Click",
        "body": "Теперь тариф можно оплатить через Click и Uzum.",
        "url": "/news/oplata",
        "tone": "success",
        "audience": "verified",
        "audience_value": "",
        **поля,
    }


def test_черновик_и_тариф(люди):
    _, без_тарифа, создана = django(
        люди["superadmin"],
        ("post", LIST + "add/", _форма(audience="plan")),
        ("post", LIST + "add/", _форма()),
    )

    assert без_тарифа["status"] == 200 and "Выберите тариф" in без_тарифа["body"]
    assert создана["status"] == 302, создана["body"][:2000]
    assert sql("select audience, audience_value, sent_at from broadcasts") == [
        ("verified", None, None)
    ]
    assert журнал("created")["section"] == "broadcasts"


def test_охват_и_отправка(люди):
    _клиенты()
    django(люди["superadmin"], ("post", LIST + "add/", _форма(audience="all")))
    [(pk,)] = sql("select id from broadcasts")

    _, страница = django(люди["superadmin"], ("get", f"{LIST}{pk}/change/", None))
    сотрудников = sql("select count(*) from users where status = 'active' and deleted_at is null")[
        0
    ][0]
    assert f"Получат сейчас: <b>{сотрудников}</b>" in страница["body"]

    _, отправлена, повтор, правка = django(
        люди["superadmin"],
        ("post", f"{LIST}{pk}/send/", {}),
        ("post", f"{LIST}{pk}/send/", {}),
        ("post", f"{LIST}{pk}/change/", _форма(title="Подменили")),
    )

    assert отправлена["status"] == 302
    assert повтор["status"] == 403 and правка["status"] == 403
    assert sql("select recipients_count, sent_at is not null, sent_by, title from broadcasts") == [
        (сотрудников, True, люди["superadmin"], "Оплата через Click")
    ]
    assert sql(
        "select count(*), bool_and(is_broadcast), max(type), max(tone) from user_notifications"
    ) == [(сотрудников, True, "broadcast", "success")]
    assert sql(
        "select count(*) from user_notifications n join users u on u.id = n.user_id "
        "where u.status = 'blocked'"
    ) == [(0,)], "заблокированным не уходит"


def test_проверенным(люди):
    _клиенты()
    django(люди["superadmin"], ("post", LIST + "add/", _форма()))
    [(pk,)] = sql("select id from broadcasts")

    django(люди["superadmin"], ("post", f"{LIST}{pk}/send/", {}))

    assert sql("select u.email from user_notifications n join users u on u.id = n.user_id") == [
        ("client-0@example.com",)
    ]


def test_контент_смотрит(люди):
    _, список, создать = django(
        люди["content_manager"], ("get", LIST, None), ("get", LIST + "add/", None)
    )

    assert список["status"] == 200
    assert создать["status"] == 403
