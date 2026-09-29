"""
Этап 7, шаг 54: колбэки Uzum на Django неотличимы от Laravel.

Merchant API (/payments/uzum/callback/<операция>): выключенный провайдер
— 404; Basic-авторизация и serviceId; check, create (повтор, сумма,
счёт оплачен или отменён), confirm (выдача тарифа или кредитов,
просроченная транзакция гасится, счёт уже оплачен), reverse, status,
неизвестная операция. Вебхук кассы (/payments/uzum/callback): белый
список адресов, пустые поля, успех перепроверяется у Uzum
(getOrderStatus — поддельный сервер), повтор не начисляет второй раз.

Время в ответах (transTime и прочие) — от мгновения ответа: сверяется,
что оно есть. База и ответы в остальном — байт в байт.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_billing_orders import Касса
from .test_web_forms import отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}
ВХОД = base64.b64encode(b"uzum:secret").decode()
ВРЕМЯ = ("transTime", "confirmTime", "reverseTime")

#: Транзакции для подготовки: свежая, просроченная, проведённая, отменённая
СВЕЖАЯ = ("SVD-000001", "created", "interval '1 minute'")
СТАРАЯ = ("SVD-000001", "created", "interval '2 hours'")
ПРОВЕДЕНА = ("SVD-000001", "performed", "interval '1 minute'")
ОТМЕНЕНА = ("SVD-000001", "cancelled", "interval '1 minute'")
СЧЁТ = {"invoice": "SVD-000001"}
ЧУЖОЙ_ВХОД = base64.b64encode(b"uzum:x").decode()


def счёт(status: str, what: str = "business") -> tuple[tuple[str, str, str], ...]:
    return (("SVD-000001", what, status),)


def настройки(касса: Касса, **extra: str) -> dict[str, str]:
    return {
        "PAYMENTS_UZUM_ENABLED": "true",
        "PAYMENTS_UZUM_CALLBACK_LOGIN": "uzum",
        "PAYMENTS_UZUM_CALLBACK_PASSWORD": "secret",
        "PAYMENTS_UZUM_SERVICE_ID": "777",
        "PAYMENTS_UZUM_BASE_URL": касса.адрес,
        "PAYMENTS_UZUM_TERMINAL_ID": "TERM-1",
        "PAYMENTS_UZUM_SECRET_KEY": "secret-key-1",
        **БЕЗ_ПЕРЕВОДА,
        **extra,
    }


@pytest.fixture(scope="module")
def касса() -> Iterator[Касса]:
    касса = Касса()
    yield касса
    касса.сервер.shutdown()


@pytest.fixture(scope="module")
def сайт(касса) -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PlanSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    php("App\\Models\\Company::factory()->create(['slug' => 'mine']);echo 'ok';", БЕЗ_ПЕРЕВОДА)
    учётка("owner@savdex.uz", company_id=_id("companies", "slug = 'mine'"))

    with laravel(**настройки(касса)) as root:
        yield root


def _id(table: str, where: str) -> int:
    return int(sql(f"select id from {table} where {where}")[0][0])


def сброс(
    *,
    счета: tuple[tuple[str, str, str], ...] = (("SVD-000001", "business", "pending"),),
    транзакция: tuple[str, str, str] | None = None,
    промокод: bool = False,
    кошелёк: bool = False,
) -> Callable[[], None]:
    """счета — (номер, тариф или «pack», статус); транзакция — (номер, состояние, возраст)."""

    def run() -> None:
        sql(
            "truncate payment_transactions, payments, promo_codes, subscriptions, wallets, "
            "wallet_transactions, user_notifications, activity_events, admin_actions "
            "restart identity cascade"
        )
        mine = _id("companies", "slug = 'mine'")

        if кошелёк:
            sql(
                "insert into wallets (company_id, credits, promo_units, created_at, updated_at) "
                "values (%s, 4, 1, now() - interval '3 days', now() - interval '3 days')",
                [mine],
            )

        if промокод:
            sql(
                "insert into promo_codes (code, plan_id, days, discount_percent, used_at, "
                "used_by_company_id, created_at, updated_at) select 'SALE', id, 0, 20, now(), "
                "%s, now() - interval '1 day', now() - interval '1 day' from plans "
                "where code = 'business'",
                [mine],
            )

        for number, what, status in счета:
            pack = what == "pack"
            sql(
                "insert into payments (company_id, purpose, plan_id, credit_pack_id, "
                "promo_code_id, description, amount, status, number, external_id, provider, "
                "created_at, updated_at) values (%s, %s, (select id from plans where code = %s), "
                "(select id from credit_packs where code = 'm' and %s), "
                "(select id from promo_codes where code = 'SALE'), %s, 1500, %s, %s, %s, "
                "'invoice', now() - interval '1 day', now() - interval '1 day')",
                [
                    mine,
                    "credits" if pack else "subscription",
                    None if pack else what,
                    pack,
                    f"Счёт «{number}» / тест",
                    status,
                    number,
                    "ORD-" + number,
                ],
            )

        if транзакция is not None:
            number, state, age = транзакция
            sql(
                "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
                "state, amount_minor, currency, performed_at, cancelled_at, created_at, "
                "updated_at) values ((select id from payments where number = %s), 'uzum', "
                f"'T-1', %s, 150000, 'UZS', case when %s = 'performed' then now() - {age} end, "
                f"case when %s = 'cancelled' then now() - {age} end, now() - {age}, now() - {age})",
                [number, state, state, state],
            )

    return run


def снимок() -> Any:
    return {
        "payments": sql(
            "select number, status, paid_at is not null, provider, external_id, "
            "subscription_id, payment_method_id from payments order by id"
        ),
        "transactions": sql(
            "select payment_id, provider, provider_transaction_id, state, amount_minor, "
            "currency, payload::text, performed_at is not null, cancelled_at is not null "
            "from payment_transactions order by id"
        ),
        "subscriptions": sql(
            "select plan_id, status, source, auto_renew, (ends_at - started_at)::text, "
            "grant_reason from subscriptions order by id"
        ),
        "wallets": sql(
            "select credits, promo_units, contacts_used_this_period from wallets order by id"
        ),
        "wallet_log": sql(
            "select kind, amount, balance_after, reason, subject_type, subject_id "
            "from wallet_transactions order by id"
        ),
        "promo": sql("select code, subscription_id from promo_codes order by id"),
        "notifications": sql("select type, title, body, tone, url from user_notifications"),
        "events": sql("select type, tone, message, url from activity_events"),
    }


def вызов(
    сайт: str,
    касса: Касса,
    path: str,
    body: Any,
    подготовка: Callable[[], None],
    *,
    вход: str | None = ВХОД,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}

    if вход is not None:
        headers["Authorization"] = "Basic " + вход

    итог = отправить(
        сайт,
        path,
        подготовка,
        снимок,
        body=body,
        headers=headers,
        env={**настройки(касса), **(env or {})},
        drop=ВРЕМЯ,
    )

    return итог


def тело(операция: str, **extra: Any) -> dict[str, Any]:
    return {"serviceId": 777, "timestamp": 1790000000000, **extra}


# ── Merchant API ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("операция", "body", "подготовка", "вход"),
    [
        ("check", {"params": СЧЁТ}, {}, ВХОД),
        ("check", {"params": СЧЁТ}, {}, None),
        ("check", {"params": СЧЁТ}, {}, ЧУЖОЙ_ВХОД),
        ("check", {"serviceId": 1, "params": СЧЁТ}, {}, ВХОД),
        ("check", {"params": {"invoice": "NOPE"}}, {}, ВХОД),
        ("check", {"params": {}}, {}, ВХОД),
        ("check", {"params": СЧЁТ}, {"счета": счёт("paid")}, ВХОД),
        ("check", {"params": СЧЁТ}, {"счета": счёт("failed")}, ВХОД),
        ("create", {"transId": "T-1", "amount": 150000, "params": СЧЁТ}, {}, ВХОД),
        ("create", {"transId": "T-1", "amount": "150000", "params": СЧЁТ}, {}, ВХОД),
        ("create", {"transId": "T-1", "amount": 100, "params": СЧЁТ}, {}, ВХОД),
        ("create", {"transId": "T-1", "amount": "x", "params": СЧЁТ}, {}, ВХОД),
        ("create", {"amount": 150000, "params": СЧЁТ}, {}, ВХОД),
        (
            "create",
            {"transId": "T-1", "amount": 150000, "params": СЧЁТ},
            {"транзакция": СВЕЖАЯ},
            ВХОД,
        ),
        ("confirm", {"transId": "T-1"}, {"транзакция": СВЕЖАЯ}, ВХОД),
        ("confirm", {"transId": "T-1"}, {"транзакция": СВЕЖАЯ, "промокод": True}, ВХОД),
        (
            "confirm",
            {"transId": "T-1"},
            {"счета": счёт("pending", "pack"), "транзакция": СВЕЖАЯ, "кошелёк": True},
            ВХОД,
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"счета": счёт("pending", "pack"), "транзакция": СВЕЖАЯ},
            ВХОД,
        ),
        ("confirm", {"transId": "T-1"}, {"транзакция": СТАРАЯ}, ВХОД),
        ("confirm", {"transId": "T-1"}, {"транзакция": ПРОВЕДЕНА}, ВХОД),
        ("confirm", {"transId": "T-1"}, {"транзакция": ОТМЕНЕНА}, ВХОД),
        ("confirm", {"transId": "T-1"}, {"счета": счёт("paid"), "транзакция": СВЕЖАЯ}, ВХОД),
        ("confirm", {"transId": "T-9"}, {}, ВХОД),
        ("reverse", {"transId": "T-1"}, {"транзакция": СВЕЖАЯ}, ВХОД),
        ("reverse", {"transId": "T-1"}, {"транзакция": ПРОВЕДЕНА}, ВХОД),
        ("reverse", {"transId": "T-1"}, {"транзакция": ОТМЕНЕНА}, ВХОД),
        ("status", {"transId": "T-1"}, {"транзакция": ПРОВЕДЕНА}, ВХОД),
        ("status", {"transId": "T-9"}, {}, ВХОД),
        ("nope", {"transId": "T-1"}, {}, ВХОД),
    ],
)
def test_merchant(сайт, касса, операция, body, подготовка, вход):
    вызов(
        сайт,
        касса,
        f"/payments/uzum/callback/{операция}",
        тело(операция, **body),
        сброс(**подготовка),
        вход=вход,
    )


@pytest.mark.parametrize("что", ["business", "pack"])
def test_подтверждение_выдаёт_купленное(сайт, касса, что):
    итог = вызов(
        сайт,
        касса,
        "/payments/uzum/callback/confirm",
        тело("confirm", transId="T-1"),
        сброс(
            счета=счёт("pending", что),
            транзакция=СВЕЖАЯ,
        ),
    )
    база = итог["база"]

    assert база["payments"][0][1:3] == ("paid", True)
    assert база["transactions"][0][3] == "performed"
    assert база["subscriptions"] if что == "business" else база["wallet_log"]
    assert база["notifications"] and база["events"]


def test_merchant_выключен(сайт, касса):
    выключен = {"PAYMENTS_UZUM_ENABLED": "false"}

    with laravel(**настройки(касса, **выключен)) as root:
        итог = вызов(
            root,
            касса,
            "/payments/uzum/callback/check",
            тело("check", params=СЧЁТ),
            сброс(),
            env=выключен,
        )

    assert итог["ответ"]["status"] == 404


# ── Вебхук кассы ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "режим", "подготовка"),
    [
        ({"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"}, "completed", {}),
        (
            {"orderId": "ORD-SVD-000001", "operationState": "success"},
            "completed",
            {"счета": (("SVD-000001", "pack", "pending"),)},
        ),
        ({"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"}, "processing", {}),
        ({"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"}, "отказ", {}),
        ({"orderId": "ORD-SVD-000001", "operationState": "FAIL"}, "completed", {}),
        ({"orderId": "SVD-000001", "operationState": "PROCESSING"}, "completed", {}),
        ({"orderId": "ORD-NOPE", "operationState": "FAIL"}, "completed", {}),
        ({"orderId": "", "operationState": "SUCCESS"}, "completed", {}),
        ({"operationState": "SUCCESS"}, "completed", {}),
        (
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            "completed",
            {"счета": (("SVD-000001", "business", "paid"),)},
        ),
    ],
)
def test_вебхук(сайт, касса, body, режим, подготовка):
    касса.режим = режим
    итог = вызов(сайт, касса, "/payments/uzum/callback", body, сброс(**подготовка), вход=None)

    if (
        режим == "completed"
        and body.get("orderId") == "ORD-SVD-000001"
        and body["operationState"] == "SUCCESS"
        and not подготовка
    ):
        assert итог["база"]["payments"][0][1] == "paid"
        assert итог["база"]["transactions"][0][3] == "performed"


def test_вебхук_повтор(сайт, касса):
    """Проведённая транзакция второй раз не проводится."""
    касса.режим = "completed"

    def подготовка() -> None:
        сброс()()
        sql(
            "insert into payment_transactions (payment_id, provider, provider_transaction_id, "
            "state, currency, performed_at, created_at, updated_at) values (1, 'uzum', "
            "'ORD-SVD-000001', 'performed', 'UZS', now(), now(), now())"
        )

    вызов(
        сайт,
        касса,
        "/payments/uzum/callback",
        {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
        подготовка,
        вход=None,
    )


def test_вебхук_чужой_адрес(сайт, касса):
    with laravel(**настройки(касса, PAYMENTS_UZUM_CALLBACK_IPS="10.0.0.1,10.0.0.2")) as root:
        вызов(
            root,
            касса,
            "/payments/uzum/callback",
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            сброс(),
            вход=None,
            env={"PAYMENTS_UZUM_CALLBACK_IPS": "10.0.0.1,10.0.0.2"},
        )


@pytest.mark.parametrize("provider", ["payme", "click"])
def test_вебхук_другой_провайдер(сайт, касса, provider):
    вызов(
        сайт,
        касса,
        f"/payments/{provider}/callback",
        {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
        сброс(),
        вход=None,
    )
