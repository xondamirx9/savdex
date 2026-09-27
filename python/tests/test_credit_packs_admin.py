"""
Раздел «Пакеты контактов» админки на Django — сквозь настоящую базу.

Три пакета заводит сама миграция Laravel (pack_10, pack_30, pack_100),
на них и проверяется: права (раздел только у суперадмина и финансов),
код, цены, запрет менять число кредитов при неоплаченных счетах,
запрет удаления пакета со счетами и строки журнала admin_actions.

Нужны PHP (миграции) и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/billing/creditpack/"
ADD = "/py/admin/billing/creditpack/add/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "finance", "admin")}


def _id(code: str) -> int:
    [(pk,)] = sql("select id from credit_packs where code = %s", [code])

    return int(pk)


def _счёт(pack: int, status: str) -> None:
    [(company,)] = sql(
        "insert into companies (name, slug, created_at, updated_at) "
        "values ('ООО «Покупатель»', 'pokupatel-' || floor(random() * 1e9)::text, now(), now()) "
        "returning id"
    )
    sql(
        "insert into payments (company_id, credit_pack_id, purpose, description, amount, "
        "status, created_at, updated_at) values (%s, %s, 'credits', 'Пакет', 100000, %s, "
        "now(), now())",
        [company, pack, status],
    )


def _форма(code: str, **поля: Any) -> dict[str, Any]:
    return {
        "code": code,
        "name": поля.get("name", "50 контактов"),
        "credits": str(поля.get("credits", 50)),
        "sort": "4",
        "price_usd": str(поля.get("price_usd", "39")),
        "price_uzs": str(поля.get("price_uzs", "")),
        "is_active": "on",
    }


def test_список_и_права(люди):
    вход, список = django(люди["finance"], ("get", LIST, None))

    assert вход == 302
    assert список["status"] == 200
    assert "30 контактов · pack_30" in список["body"]
    assert "$24 по курсу" in список["body"]

    # Администратору площадки пакеты не выданы — только суперадмину и финансам
    _, чужой = django(люди["admin"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_пакета_и_журнал(люди):
    _, ответ = django(люди["finance"], ("post", ADD, _форма(" Pack_50 ", price_uzs="450000")))

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert sql(
        "select credits, price_usd::text, price_uzs from credit_packs where code = 'pack_50'"
    ) == [(50, "39.00", 450000)]

    запись = журнал("created")
    assert запись["user_role"] == "finance"
    assert запись["section"] == "creditpacks"
    assert запись["subject_type"] == "App\\Models\\CreditPack"
    assert запись["changes"]["after"]["price_usd"] == "39.00"


@pytest.mark.parametrize(
    ("поля", "ошибка"),
    [
        ({"price_usd": "-5"}, "Цена должна быть больше нуля."),
        ({"price_usd": "0"}, "Цена должна быть больше нуля."),
        ({"price_uzs": "0"}, "Цена должна быть больше нуля — или оставьте пустым."),
        ({"credits": 0}, "Хотя бы один кредит."),
    ],
)
def test_цены_и_кредиты_больше_нуля(люди, поля, ошибка):
    _, ответ = django(люди["finance"], ("post", ADD, _форма("pack_bad", **поля)))

    assert ответ["status"] == 200
    assert ошибка in ответ["body"]


@pytest.mark.parametrize("code", ["пакет", "pack 5", "PACK_10"])
def test_код_латиницей_и_без_повторов(люди, code):
    _, ответ = django(люди["finance"], ("post", ADD, _форма(code)))

    assert ответ["status"] == 200
    assert "Только латиница" in ответ["body"] or "Пакет с таким кодом уже есть" in ответ["body"]


def test_число_кредитов_не_меняется_при_неоплаченных_счетах(люди):
    """
    Кредиты начисляются по пакету, а не по счёту: заплативший за
    «30 контактов» получил бы другое число.
    """
    pk = _id("pack_30")
    _счёт(pk, "pending")

    _, отказ = django(
        люди["finance"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма("pack_30", name="30 контактов", credits=25, price_usd="24"),
        ),
    )
    assert отказ["status"] == 200
    assert "На пакет выставлено неоплаченных счетов: 1" in отказ["body"]
    assert sql("select credits from credit_packs where id = %s", [pk]) == [(30,)]

    # Цену менять можно: сумма уже записана в счёте
    _, цена = django(
        люди["finance"],
        (
            "post",
            f"{LIST}{pk}/change/",
            _форма("pack_30", name="30 контактов", credits=30, price_usd="22"),
        ),
    )
    assert цена["status"] == 302, цена["body"][:3000]
    assert журнал("updated")["changes"] == {
        "before": {"price_usd": "24.00", "sort": 2},
        "after": {"price_usd": "22.00", "sort": 4},
    }


def test_удаление(люди):
    pack_10, pack_50 = _id("pack_10"), _id("pack_50")
    _счёт(pack_10, "paid")

    _, форма, занятый = django(
        люди["superadmin"],
        ("get", f"{LIST}{pack_10}/change/", None),
        ("post", f"{LIST}{pack_10}/delete/", {"post": "yes"}),
    )
    assert "Нельзя, на пакет ссылаются: счета — 1" in форма["body"]
    assert занятый["status"] == 403
    assert sql("select count(*) from credit_packs where id = %s", [pack_10]) == [(1,)]

    _, свободный = django(люди["superadmin"], ("post", f"{LIST}{pack_50}/delete/", {"post": "yes"}))
    assert свободный["status"] == 302
    assert sql("select count(*) from credit_packs where id = %s", [pack_50]) == [(0,)]
    # Название в журнале — как у Laravel: имя записи, а не код
    assert журнал("deleted")["subject_label"] == "50 контактов"
