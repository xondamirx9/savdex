"""
Раскрытие контактов на визитке на Django неотличимо от Laravel: расход
лимита тарифа, сверх него — кредит с записью в историю кошелька; нет ни
того ни другого — отказ с датой обновления лимита. Повторное раскрытие
бесплатно, свои контакты не покупают, заблокированным — отказ, без
кошелька — отказ. Объявление — только для статистики: чужое и
несуществующее не мешают. Уведомление компании, чьи контакты открыли.

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


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'buyer', 'name' => 'Покупатель']);"
        "$t = App\\Models\\Company::factory()->create(['slug' => 'target', 'name' => 'Цемент']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "App\\Models\\Listing::factory()->create(['company_id' => $t->id,"
        " 'title' => 'Цемент М400', 'status' => 'active']);"
        "App\\Models\\Listing::factory()->create(['company_id' => $o->id,"
        " 'title' => 'Чужое', 'status' => 'active']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    учётка("target@savdex.uz", company_id=_id("target"))

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def _id(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def _объявление(slug: str) -> int:
    return int(
        sql(
            "select l.id from listings l join companies c on c.id = l.company_id "
            "where c.slug = %s order by l.id limit 1",
            [slug],
        )[0][0]
    )


def покупатель(*, admin: bool = False, company: bool = True, status: str = "active") -> int:
    return учётка(
        "buyer@savdex.uz",
        company_id=_id("buyer") if company else None,
        is_admin=admin,
        status=status,
        email_verified_at="2026-09-01 10:00:00",
    )


def сброс(
    *,
    лимит: int | None = 3,
    израсходовано: int = 0,
    кредиты: int = 0,
    кошелёк: bool = True,
    обновится: bool = True,
    открыт: bool = False,
    блок: str | None = None,
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from contact_unlocks")
        sql("delete from wallet_transactions")
        sql("delete from wallets")
        sql("delete from listing_stats")
        sql("delete from activity_events")
        sql("delete from user_notifications")
        sql("delete from admin_actions")
        sql("update listings set unlocks_count = 0, updated_at = now() - interval '1 day'")
        sql("update plans set contacts_limit = %s where code = 'free'", [лимит])
        sql("update companies set status = 'active'")
        # Префикс /en меняет язык учётки: у обоих сайтов начинаем с ru
        sql("update users set locale = 'ru'")

        if блок is not None:
            sql("update companies set status = 'blocked' where slug = %s", [блок])

        if кошелёк:
            sql(
                "insert into wallets (company_id, credits, contacts_used_this_period, "
                "period_resets_at, created_at, updated_at) values (%s, %s, %s, %s, "
                "now() - interval '1 day', now() - interval '1 day')",
                [
                    _id("buyer"),
                    кредиты,
                    израсходовано,
                    "2026-10-15 00:00:00" if обновится else None,
                ],
            )

        if открыт:
            sql(
                "insert into contact_unlocks (company_id, target_company_id, credits_spent, "
                "status, created_at, updated_at) values (%s, %s, 1, 'new', now(), now())",
                [_id("buyer"), _id("target")],
            )

    return run


def снимок() -> Any:
    return {
        "unlocks": sql(
            "select company_id, target_company_id, user_id is not null, listing_id, "
            "credits_spent, status from contact_unlocks order by id"
        ),
        "wallets": sql(
            "select credits, contacts_used_this_period, "
            "updated_at > now() - interval '1 hour' from wallets order by id"
        ),
        "transactions": sql(
            "select company_id, user_id is not null, kind, amount, balance_after, reason, "
            "subject_type, subject_id from wallet_transactions order by id"
        ),
        "listings": sql(
            "select id, unlocks_count, updated_at > now() - interval '1 hour' "
            "from listings order by id"
        ),
        "stats": sql("select listing_id, unlocks, views from listing_stats order by listing_id"),
        "events": sql("select company_id, type, tone, message, url from activity_events"),
        "notifications": sql(
            "select user_id, type, title, body, tone, url from user_notifications order by id"
        ),
        "journal": sql(
            "select action, section, subject_type, subject_label, changes::text "
            "from admin_actions order by id"
        ),
    }


@pytest.mark.parametrize(
    "подготовка",
    [
        {},
        {"лимит": None, "израсходовано": 50},
        {"израсходовано": 3, "кредиты": 2},
        {"израсходовано": 3},
        {"израсходовано": 5, "обновится": False},
        {"открыт": True},
        {"кошелёк": False},
        {"блок": "buyer"},
        {"блок": "target"},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_раскрытие(сайт, подготовка, admin):
    итог = отправить(
        сайт,
        "/company/target/unlock",
        сброс(**подготовка),
        снимок,
        uid=покупатель(admin=admin),
        headers=inertia(),
    )

    if not подготовка:
        assert итог["база"]["unlocks"] and итог["база"]["notifications"]


@pytest.mark.parametrize(
    "listing",
    ["своё", "чужое", "999999", "abc", "", ["x"], True, 1.9],
)
@pytest.mark.parametrize("admin", [False, True])
def test_объявление(сайт, listing, admin):
    значение: Any = listing

    if listing == "своё":
        значение = str(_объявление("target"))
    elif listing == "чужое":
        значение = _объявление("other")

    итог = отправить(
        сайт,
        "/en/company/target/unlock",
        сброс(),
        снимок,
        uid=покупатель(admin=admin),
        body={"listing_id": значение},
        headers=inertia(),
    )

    if listing == "своё":
        assert итог["база"]["stats"]


@pytest.mark.parametrize("случай", ["своя", "без компании", "заблокирован", "нет такой"])
def test_отказ(сайт, случай):
    uid = покупатель(
        company=случай != "без компании",
        status="blocked" if случай == "заблокирован" else "active",
    )
    slug = {"своя": "buyer", "нет такой": "missing"}.get(случай, "target")
    отправить(
        сайт,
        f"/company/{slug}/unlock",
        сброс(),
        снимок,
        uid=uid,
        headers=inertia(),
    )


def test_почта(сайт):
    uid = покупатель()
    sql("update users set email_verified_at = null where id = %s", [uid])

    try:
        отправить(сайт, "/company/target/unlock", сброс(), снимок, uid=uid, headers=inertia())
    finally:
        sql("update users set email_verified_at = now() where id = %s", [uid])
