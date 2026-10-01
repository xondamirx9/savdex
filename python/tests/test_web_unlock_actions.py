"""
Раскрытие контактов на визитке — проверки Django: расход
лимита тарифа, сверх него — кредит с записью в историю кошелька; нет ни
того ни другого — отказ с датой обновления лимита. Повторное раскрытие
бесплатно, свои контакты не покупают, заблокированным — отказ, без
кошелька — отказ. Объявление — только для статистики: чужое и
несуществующее не мешают. Уведомление компании, чьи контакты открыли.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания, объявление
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    # Бесплатный тариф: 3 контакта в месяц (лимит правит сброс())
    sql(
        "insert into plans (code, name, price_usd, period_days, listing_days, listings_limit, "
        "contacts_limit, promo_units, verification_days, sort, is_active, created_at, "
        "updated_at) values ('free', 'Free', 0, 30, 30, 4, 3, 0, 5, 1, true, now(), now())"
    )
    компания(slug="buyer", name="Покупатель")
    target = компания(slug="target", name="Цемент")
    other = компания(slug="other")
    объявление(company_id=target, title="Цемент М400", status="active")
    объявление(company_id=other, title="Чужое", status="active")
    учётка("target@savdex.uz", company_id=target)

    with адрес() as root:
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


УСПЕХ = (
    "Контакты открыты. Доступ сохраняется навсегда — платить второй раз за эту компанию не нужно."
)
ИСЧЕРПАН = "Лимит контактов по тарифу исчерпан, кредитов на счету нет."
КУПИТЕ = "Купите пакет кредитов или смените тариф."
ОТКРЫЛА = "Компания «Покупатель» открыла ваши контакты"
ЛИД = "Это тёплый лид: за контакт заплатили."


def сообщение(итог: dict[str, Any]) -> dict[str, str]:
    """Сообщение после перехода назад: {"success": …} или {"error": …}."""
    payload = json.loads(итог["сессия"]["payload"])

    return {k: payload[k] for k in ("success", "error") if k in payload}


def открыто(итог: dict[str, Any], *, spent: int, listing: int | None = None) -> None:
    """Раскрытие записано, компании, чьи контакты открыли, — событие и уведомление."""
    база = итог["база"]
    target = _id("target")
    [(сотрудник,)] = sql("select id from users where company_id = %s", [target])
    тело = f"По объявлению «Цемент М400». {ЛИД}" if listing else ЛИД

    assert база["unlocks"] == [(_id("buyer"), target, True, listing, spent, "new")]
    assert база["events"] == [(target, "contact_unlocked", "success", ОТКРЫЛА, "/cabinet/incoming")]
    assert база["notifications"] == [
        (сотрудник, "contact_unlocked", ОТКРЫЛА, тело, "success", "/cabinet/incoming")
    ]


@pytest.mark.parametrize(
    ("подготовка", "кошелёк", "итог_"),
    [
        # Расход лимита тарифа
        ({}, [(0, 1, True)], {"success": УСПЕХ}),
        # Тариф без лимита
        ({"лимит": None, "израсходовано": 50}, [(0, 51, True)], {"success": УСПЕХ}),
        # Сверх лимита — кредит с записью в историю
        ({"израсходовано": 3, "кредиты": 2}, [(1, 3, True)], {"success": УСПЕХ}),
        # Ни лимита, ни кредитов — отказ с датой обновления лимита
        (
            {"израсходовано": 3},
            [(0, 3, False)],
            {"error": f"{ИСЧЕРПАН} Лимит обновится 15.10.2026. {КУПИТЕ}"},
        ),
        (
            {"израсходовано": 5, "обновится": False},
            [(0, 5, False)],
            {"error": f"{ИСЧЕРПАН} {КУПИТЕ}"},
        ),
        # Повторное раскрытие бесплатно
        (
            {"открыт": True},
            [(0, 0, False)],
            {"success": "Контакты этой компании у вас уже открыты."},
        ),
        ({"кошелёк": False}, [], {"error": "Кошелёк компании не найден. Напишите в поддержку."}),
        (
            {"блок": "buyer"},
            [(0, 0, False)],
            {"error": "Ваша компания заблокирована, раскрытие контактов недоступно."},
        ),
        (
            {"блок": "target"},
            [(0, 0, False)],
            {"error": "Компания заблокирована, её контакты недоступны."},
        ),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_раскрытие(сайт, подготовка, кошелёк, итог_, admin):
    итог = отправить(
        сайт,
        "/company/target/unlock",
        сброс(**подготовка),
        снимок,
        uid=покупатель(admin=admin),
        headers=inertia(),
    )
    база = итог["база"]

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    assert сообщение(итог) == итог_
    assert база["wallets"] == кошелёк
    # Объявление не указано — статистика не трогается
    assert [row[1:] for row in база["listings"]] == [(0, False), (0, False)]
    assert база["stats"] == [] and база["journal"] == []

    if "success" in итог_ and not подготовка.get("открыт"):
        открыто(итог, spent=1 if подготовка.get("кредиты") else 0)
    else:
        assert база["events"] == база["notifications"] == []
        assert база["unlocks"] == (
            [(_id("buyer"), _id("target"), False, None, 1, "new")]
            if подготовка.get("открыт")
            else []
        )

    if подготовка.get("кредиты"):
        assert база["transactions"] == [
            (_id("buyer"), True, "credits", -1, 1, "unlock", "App\\Models\\Company", _id("target"))
        ]
    else:
        assert база["transactions"] == []


@pytest.mark.parametrize(
    ("listing", "учтено"),
    [
        ("своё", True),
        # Чужое и несуществующее не мешают раскрытию — только не учитываются
        ("чужое", False),
        ("999999", False),
        ("abc", False),
        ("", False),
        # Как (int) у PHP: массив, true и 1.9 — номер 1, это объявление компании
        (["x"], True),
        (True, True),
        (1.9, True),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_объявление(сайт, listing, учтено, admin):
    значение: Any = listing
    своё = _объявление("target")
    assert своё == 1

    if listing == "своё":
        значение = str(своё)
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
    база = итог["база"]

    assert итог["ответ"]["headers"]["location"] == сайт + "/en/cabinet/settings"
    assert сообщение(итог) == {
        "success": "Contacts unlocked. Access stays forever — "
        "you will not pay twice for this company."
    }
    открыто(итог, spent=0, listing=своё if учтено else None)
    assert база["wallets"] == [(0, 1, True)]
    assert база["listings"] == [
        (своё, 1 if учтено else 0, учтено),
        (_объявление("other"), 0, False),
    ]
    assert база["stats"] == ([(своё, 1, 0)] if учтено else [])

    # Администратору — строки журнала: язык из адреса и счётчик объявления
    журнал = [
        (
            "updated",
            "users",
            "App\\Models\\User",
            "Покупатель buyer@savdex.uz",
            '{"before":{"locale":"ru"},"after":{"locale":"en"}}',
        )
    ]
    if учтено:
        журнал.append(
            (
                "updated",
                "listings",
                "App\\Models\\Listing",
                "Цемент М400",
                '{"before":{"unlocks_count":0},"after":{"unlocks_count":1}}',
            )
        )
    assert база["journal"] == (журнал if admin else [])


@pytest.mark.parametrize(
    ("случай", "status", "ошибка"),
    [
        ("своя", 302, "Это контакты вашей компании."),
        ("без компании", 302, "Сначала заполните данные компании — раскрытие идёт от её имени."),
        ("заблокирован", 302, "Ваша учётная запись заблокирована. Напишите в поддержку."),
        ("нет такой", 404, None),
    ],
)
def test_отказ(сайт, случай, status, ошибка):
    uid = покупатель(
        company=случай != "без компании",
        status="blocked" if случай == "заблокирован" else "active",
    )
    slug = {"своя": "buyer", "нет такой": "missing"}.get(случай, "target")
    итог = отправить(
        сайт,
        f"/company/{slug}/unlock",
        сброс(),
        снимок,
        uid=uid,
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == status
    assert сообщение(итог) == ({"error": ошибка} if ошибка else {})
    assert итог["база"]["unlocks"] == итог["база"]["notifications"] == []
    assert итог["база"]["wallets"] == [(0, 0, False)]


def test_почта(сайт):
    uid = покупатель()
    sql("update users set email_verified_at = null where id = %s", [uid])

    try:
        итог = отправить(
            сайт, "/company/target/unlock", сброс(), снимок, uid=uid, headers=inertia()
        )
    finally:
        sql("update users set email_verified_at = now() where id = %s", [uid])

    # Неподтверждённая почта — на подтверждение, раскрытия нет
    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert итог["база"]["unlocks"] == [] and итог["база"]["wallets"] == [(0, 0, False)]
