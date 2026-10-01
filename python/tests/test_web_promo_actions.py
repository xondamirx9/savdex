"""
Продвижение объявления на Django: только активное
своё объявление, дважды одно и то же не продаётся, места в категории,
нет кошелька, не хватает единиц; успех — списание с записью в историю
кошелька, строка продвижения со сроком и active_key, уведомление.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import категория, компания, объявление
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    c = компания(slug="mine")
    o = компания(slug="other")
    cat = категория(slug="cement")

    for who, status, title in (
        (c, "active", "Цемент М400"),
        (c, "archived", "Старое"),
        (o, "active", "Чужое"),
    ):
        объявление(
            company_id=who, category_id=cat, status=status, title=title, impressions_count=120
        )

    for code, name, cost, days, slots in (
        ("top", "Поднятие в топ", 3, 7, 1),
        ("badge", "Значок", 2, 0, None),
    ):
        sql(
            "insert into promotion_types (code, name, description, cost_units, duration_days, "
            "slots, created_at, updated_at) values (%s, %s, 'x', %s, %s, %s, now(), now())",
            [code, name, cost, days, slots],
        )

    with адрес() as root:
        yield root


def _id(table: str, where: str) -> int:
    return int(sql(f"select id from {table} where {where}")[0][0])


def владелец(admin: bool = False) -> int:
    return учётка("owner@savdex.uz", company_id=_id("companies", "slug = 'mine'"), is_admin=admin)


def сброс(
    *, единиц: int | None = 10, запущено: str | None = None, занято: bool = False
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from promotions")
        sql("delete from wallet_transactions")
        sql("delete from wallets")
        sql("delete from activity_events")
        sql("delete from user_notifications")
        sql("update users set locale = 'ru'")
        mine = _id("companies", "slug = 'mine'")

        if единиц is not None:
            sql(
                "insert into wallets (company_id, promo_units, created_at, updated_at) "
                "values (%s, %s, now() - interval '1 day', now() - interval '1 day')",
                [mine, единиц],
            )

        def запуск(company: str, code: str) -> None:
            sql(
                "insert into promotions (listing_id, company_id, promotion_type_id, "
                "category_id, units_spent, status, starts_at, active_key, created_at, "
                "updated_at) select l.id, l.company_id, t.id, l.category_id, 1, 'active', "
                "now(), l.id || ':' || t.id, now(), now() from listings l, promotion_types t "
                "where l.company_id = %s and l.status = 'active' and t.code = %s",
                [_id("companies", f"slug = '{company}'"), code],
            )

        if запущено is not None:
            запуск("mine", запущено)

        if занято:
            запуск("other", "top")

    return run


def снимок() -> Any:
    return {
        "promotions": sql(
            "select listing_id, company_id, promotion_type_id, category_id, units_spent, "
            "status, starts_at > now() - interval '1 hour', "
            "(ends_at - starts_at)::text, impressions_before, active_key "
            "from promotions order by id"
        ),
        "wallets": sql("select promo_units, credits from wallets order by id"),
        "transactions": sql(
            "select kind, amount, balance_after, reason, subject_type, user_id is not null "
            "from wallet_transactions order by id"
        ),
        "events": sql(
            "select type, tone, message, regexp_replace(url, ':[0-9]+', '') "
            "from activity_events order by id"
        ),
        "notifications": sql(
            "select type, title, tone, regexp_replace(url, ':[0-9]+', '') "
            "from user_notifications order by id"
        ),
    }


def _listing(title: str) -> int:
    return _id("listings", f"title = '{title}'")


def _type(code: str) -> int:
    return _id("promotion_types", f"code = '{code}'")


@pytest.mark.parametrize(
    ("что", "подготовка", "ошибка"),
    [
        (("Цемент М400", "top"), {}, None),
        (("Цемент М400", "badge"), {}, None),
        (("Цемент М400", "top"), {"единиц": 2}, "Не хватает единиц продвижения: нужно 3, есть 2"),
        (("Цемент М400", "top"), {"единиц": None}, "Кошелёк компании не найден."),
        (
            ("Цемент М400", "top"),
            {"запущено": "top"},
            "«Поднятие в топ» уже действует на этом объявлении",
        ),
        # Другое продвижение того же объявления — можно
        (("Цемент М400", "badge"), {"запущено": "top"}, None),
        # Единственное место в категории занято чужим объявлением
        (("Цемент М400", "top"), {"занято": True}, "Все места «Поднятие в топ» заняты."),
        (("Старое", "top"), {}, "Продвигать можно только активные объявления"),
        (("Чужое", "top"), {}, "Продвигать можно только активные объявления"),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_продвижение(сайт, что, подготовка, ошибка, admin):
    title, code = что
    итог = отправить(
        сайт,
        "/cabinet/promo",
        сброс(**подготовка),
        снимок,
        uid=владелец(admin),
        body={"listing_id": _listing(title), "promotion_type_id": _type(code)},
        headers=inertia(),
    )

    сессия = json.loads(итог["сессия"]["payload"])
    база = итог["база"]
    было = подготовка.get("единиц", 10)
    уже = 1 if подготовка.get("запущено") or подготовка.get("занято") else 0

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"].endswith("/cabinet/settings")

    if ошибка is not None:
        assert сессия["error"].startswith(ошибка), сессия["error"]
        assert len(база["promotions"]) == уже
        assert база["wallets"] == ([] if было is None else [(было, 0)])
        assert not база["transactions"] and not база["events"] and not база["notifications"]

        return

    имя, цена, дней = {"top": ("Поднятие в топ", 3, "7 days"), "badge": ("Значок", 2, None)}[code]
    lid = _listing(title)

    assert сессия["success"] == f"«{имя}» запущено. Списано единиц: {цена}."
    # Строка продвижения: срок, показы до старта, ключ «объявление:вид»
    assert база["promotions"][-1] == (
        lid,
        _id("companies", "slug = 'mine'"),
        _type(code),
        _id("categories", "slug = 'cement'"),
        цена,
        "active",
        True,
        дней,
        120,
        f"{lid}:{_type(code)}",
    )
    assert база["wallets"] == [(10 - цена, 0)]
    assert база["transactions"] == [
        ("promo_units", -цена, 10 - цена, "promotion", "App\\Models\\Listing", True)
    ]
    сообщение = f"Запущено продвижение «{имя}» на объявлении «{title}»"
    assert [(e[0], e[1], e[2]) for e in база["events"]] == [("promotion", "success", сообщение)]
    assert [(n[0], n[1], n[2]) for n in база["notifications"]] == [
        ("promotion", сообщение, "success")
    ]


@pytest.mark.parametrize(
    ("body", "ошибки"),
    [
        (
            {},
            {
                "listing_id": ["Choose a listing"],
                "promotion_type_id": ["The promotion type id field is required."],
            },
        ),
        (
            {"listing_id": "abc", "promotion_type_id": 999},
            {
                "listing_id": ["The listing id field must be an integer."],
                "promotion_type_id": ["The selected promotion type id is invalid."],
            },
        ),
        (
            {"listing_id": 999999, "promotion_type_id": 999},
            {"promotion_type_id": ["The selected promotion type id is invalid."]},
        ),
    ],
)
def test_ошибки(сайт, body, ошибки):
    итог = отправить(
        сайт, "/en/cabinet/promo", сброс(), снимок, uid=владелец(), body=body, headers=inertia()
    )
    сессия = json.loads(итог["сессия"]["payload"])

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"].endswith("/en/cabinet/settings")
    assert сессия["errors"]["default"]["messages"] == ошибки
    assert not итог["база"]["promotions"] and итог["база"]["wallets"] == [(10, 0)]
