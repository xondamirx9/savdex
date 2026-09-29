"""
Этап 7, шаг 53: формы кассы на Django неотличимы от Laravel —
отмена и включение автопродления, отвязка карты, отказ от счёта.

Нет подписки — 404; включить можно только оплаченную; основную карту
при автопродлении не отвязать; чужая карта и чужой или уже оплаченный
счёт — 404; отменённый счёт возвращает скидочный промокод, если по нему
нет живой карточной транзакции. У администратора — строка журнала.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
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
    *,
    подписка: str | None = "payment",
    автопродление: bool = True,
    конец: str | None = "now() + interval '20 days'",
    промокод: bool = False,
    транзакция: str | None = None,
) -> Callable[[], None]:
    def run() -> None:
        # Номера с единицы: карта и счёт в адресе — те же у обеих сторон
        sql(
            "truncate payment_transactions, payments, promo_codes, payment_methods, "
            "subscriptions, admin_actions restart identity cascade"
        )
        # Язык из адреса (/en/…) правит учётку — у каждой стороны заново
        sql("update users set locale = 'ru'")

        mine = _id("companies", "slug = 'mine'")
        other = _id("companies", "slug = 'other'")
        plan = _id("plans", "code = 'business'")

        if подписка is not None:
            sql(
                "insert into subscriptions (company_id, plan_id, status, source, auto_renew, "
                "started_at, ends_at, created_at, updated_at) values (%s, %s, 'active', %s, %s, "
                f"now() - interval '10 days', {конец or 'null'}, now() - interval '10 days', "
                "now() - interval '10 days')",
                [mine, plan, подписка, автопродление],
            )

        for company, token, default in ((mine, "a", True), (mine, "b", False), (other, "c", True)):
            sql(
                "insert into payment_methods (company_id, provider, token, brand, last4, "
                "is_default, created_at, updated_at) values (%s, 'uzum', %s, 'Humo', '1234', "
                "%s, now(), now())",
                [company, token, default],
            )

        code = None

        if промокод:
            sql(
                "insert into promo_codes (code, plan_id, days, discount_percent, used_at, "
                "used_by_company_id, created_at, updated_at) values ('SALE20', %s, 30, 20, "
                "now(), %s, now() - interval '1 day', now() - interval '1 day')",
                [plan, mine],
            )
            code = _id("promo_codes", "code = 'SALE20'")

        for company, number, status in (
            (mine, "SVX-1", "pending"),
            (mine, "SVX-2", "paid"),
            (other, "SVX-3", "pending"),
        ):
            sql(
                "insert into payments (company_id, purpose, description, amount, currency, "
                "status, number, promo_code_id, admin_note, created_at, updated_at) values "
                "(%s, 'plan', 'Тариф', 1000000, 'UZS', %s, %s, %s, 'заметка', "
                "now() - interval '2 days', now() - interval '2 days')",
                [company, status, number, code if number == "SVX-1" else None],
            )

        if транзакция is not None:
            sql(
                "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
                "state, amount_minor, created_at, updated_at) values (%s, 'uzum', 'T1', "
                "'created', 100000000, "
                f"{транзакция}, {транзакция})",
                [_id("payments", "number = 'SVX-1'")],
            )

    return run


def снимок() -> Any:
    return {
        "subscriptions": sql(
            "select auto_renew, cancelled_at is not null, "
            "cancelled_at > now() - interval '1 minute', updated_at > now() - interval '1 minute' "
            "from subscriptions order by id"
        ),
        "cards": sql("select token from payment_methods order by id"),
        "payments": sql(
            "select number, status, confirmed_by, admin_note, "
            "updated_at > now() - interval '1 minute' from payments order by id"
        ),
        "promo": sql(
            "select used_at is null, used_by_company_id, used_by_user_id, "
            "updated_at > now() - interval '1 minute' from promo_codes order by id"
        ),
        "journal": sql(
            "select action, section, subject_type, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


@pytest.mark.parametrize(
    "подготовка",
    [
        {},
        {"автопродление": False},
        {"конец": None},
        {"подписка": None},
        {"конец": "now() - interval '1 day'"},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_отмена_автопродления(сайт, подготовка, admin):
    итог = отправить(
        сайт, "/cabinet/billing/cancel", сброс(**подготовка), снимок, uid=владелец(admin)
    )

    if not подготовка:
        assert итог["база"]["subscriptions"][0][0] is False


@pytest.mark.parametrize(
    "подготовка",
    [
        {"автопродление": False},
        {},
        {"подписка": "promo"},
        {"подписка": "manual"},
        {"подписка": None},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_включение_автопродления(сайт, подготовка, admin):
    отправить(сайт, "/en/cabinet/billing/resume", сброс(**подготовка), снимок, uid=владелец(admin))


def _карта(token: str) -> int:
    return _id("payment_methods", f"token = '{token}'")


@pytest.mark.parametrize(
    ("карта", "подготовка"),
    [
        ("a", {}),
        ("a", {"автопродление": False}),
        ("a", {"подписка": None}),
        ("b", {}),
        ("c", {}),
        (None, {}),
    ],
)
def test_отвязка_карты(сайт, карта, подготовка):
    сброс(**подготовка)()
    номер = _карта(карта) if карта else 999999
    отправить(
        сайт,
        f"/cabinet/billing/card/{номер}",
        сброс(**подготовка),
        снимок,
        uid=владелец(),
        method="DELETE",
    )


def _счёт(number: str) -> int:
    return _id("payments", f"number = '{number}'")


@pytest.mark.parametrize(
    ("счёт", "подготовка"),
    [
        ("SVX-1", {}),
        ("SVX-1", {"промокод": True}),
        ("SVX-1", {"промокод": True, "транзакция": "now() - interval '5 minutes'"}),
        ("SVX-1", {"промокод": True, "транзакция": "now() - interval '2 hours'"}),
        ("SVX-2", {}),
        ("SVX-3", {}),
        (None, {}),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_отказ_от_счёта(сайт, счёт, подготовка, admin):
    сброс(**подготовка)()
    номер = _счёт(счёт) if счёт else 999999
    итог = отправить(
        сайт,
        f"/uz/cabinet/billing/invoice/{номер}/cancel",
        сброс(**подготовка),
        снимок,
        uid=владелец(admin),
        headers=inertia(),
    )

    if счёт == "SVX-1" and len(подготовка) == 1:
        assert итог["база"]["promo"][0][:2] == (True, None)


def test_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz")

    for path, method in (
        ("/cabinet/billing/cancel", "POST"),
        ("/cabinet/billing/resume", "POST"),
        ("/cabinet/billing/card/1", "DELETE"),
        ("/cabinet/billing/invoice/1/cancel", "POST"),
    ):
        отправить(сайт, path, сброс(), снимок, uid=uid, method=method)


def test_гость(сайт):
    отправить(сайт, "/cabinet/billing/cancel", сброс(), снимок)
