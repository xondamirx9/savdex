"""
Продвижение объявления на Django неотличимо от Laravel: только активное
своё объявление, дважды одно и то же не продаётся, места в категории,
нет кошелька, не хватает единиц; успех — списание с записью в историю
кошелька, строка продвижения со сроком и active_key, уведомление.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "$cat = App\\Models\\Category::factory()->create(['slug' => 'cement']);"
        "foreach ([[$c, 'active', 'Цемент М400'], [$c, 'archived', 'Старое'],"
        " [$o, 'active', 'Чужое']] as [$who, $status, $title]) {"
        " App\\Models\\Listing::factory()->create(['company_id' => $who->id,"
        " 'category_id' => $cat->id, 'status' => $status, 'title' => $title,"
        " 'impressions_count' => 120]); }"
        "App\\Models\\PromotionType::create(['code' => 'top', 'name' => 'Поднятие в топ',"
        " 'description' => 'x', 'cost_units' => 3, 'duration_days' => 7, 'slots' => 1]);"
        "App\\Models\\PromotionType::create(['code' => 'badge', 'name' => 'Значок',"
        " 'description' => 'x', 'cost_units' => 2, 'duration_days' => 0]);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
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
    ("что", "подготовка"),
    [
        (("Цемент М400", "top"), {}),
        (("Цемент М400", "badge"), {}),
        (("Цемент М400", "top"), {"единиц": 2}),
        (("Цемент М400", "top"), {"единиц": None}),
        (("Цемент М400", "top"), {"запущено": "top"}),
        (("Цемент М400", "badge"), {"запущено": "top"}),
        (("Цемент М400", "top"), {"занято": True}),
        (("Старое", "top"), {}),
        (("Чужое", "top"), {}),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_продвижение(сайт, что, подготовка, admin):
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

    if not подготовка and title == "Цемент М400":
        assert len(итог["база"]["promotions"]) == 1 and итог["база"]["transactions"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"listing_id": "abc", "promotion_type_id": 999},
        {"listing_id": 999999, "promotion_type_id": 999},
    ],
)
def test_ошибки(сайт, body):
    отправить(
        сайт, "/en/cabinet/promo", сброс(), снимок, uid=владелец(), body=body, headers=inertia()
    )
