"""
Этап 7, шаг 54: колбэки Uzum на Django.

Merchant API (/payments/uzum/callback/<операция>): выключенный провайдер
— 404; Basic-авторизация и serviceId; check, create (повтор, сумма,
счёт оплачен или отменён), confirm (выдача тарифа или кредитов,
просроченная транзакция гасится, счёт уже оплачен), reverse, status,
неизвестная операция. Вебхук кассы (/payments/uzum/callback): белый
список адресов, пустые поля, успех перепроверяется у Uzum
(getOrderStatus — поддельный сервер), повтор не начисляет второй раз.

Время в ответах (transTime и прочие) — от мгновения ответа: проверяется,
что оно есть.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_billing_orders import Касса
from .test_web_catalog import справочники
from .test_web_forms import отправить, учётка
from .web_site import адрес

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
    справочники("plans")
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    компания(slug="mine")
    учётка("owner@savdex.uz", company_id=_id("companies", "slug = 'mine'"))

    with адрес() as root:
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


def ответ(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["ответ"]["body"]))


# ── Merchant API ────────────────────────────────────────────────────

#: Время операции в ответе — по её итогу
ВРЕМЯ_ИТОГА = {"CREATED": "transTime", "CONFIRMED": "confirmTime", "REVERSED": "reverseTime"}


@pytest.mark.parametrize(
    ("операция", "body", "подготовка", "вход", "итог_", "счёт_", "транзакция_"),
    [
        ("check", {"params": СЧЁТ}, {}, ВХОД, (200, "OK"), "pending", None),
        # Без входа и с чужим — 401
        ("check", {"params": СЧЁТ}, {}, None, (401, 10001), "pending", None),
        ("check", {"params": СЧЁТ}, {}, ЧУЖОЙ_ВХОД, (401, 10001), "pending", None),
        # Чужой serviceId, нет счёта, нет номера счёта
        ("check", {"serviceId": 1, "params": СЧЁТ}, {}, ВХОД, (400, 10006), "pending", None),
        ("check", {"params": {"invoice": "NOPE"}}, {}, ВХОД, (400, 10007), "pending", None),
        ("check", {"params": {}}, {}, ВХОД, (400, 10005), "pending", None),
        # Счёт уже оплачен или отменён
        ("check", {"params": СЧЁТ}, {"счета": счёт("paid")}, ВХОД, (400, 10008), "paid", None),
        ("check", {"params": СЧЁТ}, {"счета": счёт("failed")}, ВХОД, (400, 10009), "failed", None),
        (
            "create",
            {"transId": "T-1", "amount": 150000, "params": СЧЁТ},
            {},
            ВХОД,
            (200, "CREATED"),
            "pending",
            "created",
        ),
        # Сумма строкой — та же
        (
            "create",
            {"transId": "T-1", "amount": "150000", "params": СЧЁТ},
            {},
            ВХОД,
            (200, "CREATED"),
            "pending",
            "created",
        ),
        # Сумма не та (в тийинах — 1500 сум = 150 000)
        (
            "create",
            {"transId": "T-1", "amount": 100, "params": СЧЁТ},
            {},
            ВХОД,
            (400, 10011),
            "pending",
            None,
        ),
        (
            "create",
            {"transId": "T-1", "amount": "x", "params": СЧЁТ},
            {},
            ВХОД,
            (400, 10005),
            "pending",
            None,
        ),
        ("create", {"amount": 150000, "params": СЧЁТ}, {}, ВХОД, (400, 10005), "pending", None),
        # Повтор create — транзакция уже есть
        (
            "create",
            {"transId": "T-1", "amount": 150000, "params": СЧЁТ},
            {"транзакция": СВЕЖАЯ},
            ВХОД,
            (400, 10010),
            "pending",
            "created",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"транзакция": СВЕЖАЯ},
            ВХОД,
            (200, "CONFIRMED"),
            "paid",
            "performed",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"транзакция": СВЕЖАЯ, "промокод": True},
            ВХОД,
            (200, "CONFIRMED"),
            "paid",
            "performed",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"счета": счёт("pending", "pack"), "транзакция": СВЕЖАЯ, "кошелёк": True},
            ВХОД,
            (200, "CONFIRMED"),
            "paid",
            "performed",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"счета": счёт("pending", "pack"), "транзакция": СВЕЖАЯ},
            ВХОД,
            (200, "CONFIRMED"),
            "paid",
            "performed",
        ),
        # Просроченная транзакция гасится
        (
            "confirm",
            {"transId": "T-1"},
            {"транзакция": СТАРАЯ},
            ВХОД,
            (400, 10015),
            "pending",
            "cancelled",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"транзакция": ПРОВЕДЕНА},
            ВХОД,
            (400, 10016),
            "pending",
            "performed",
        ),
        (
            "confirm",
            {"transId": "T-1"},
            {"транзакция": ОТМЕНЕНА},
            ВХОД,
            (400, 10015),
            "pending",
            "cancelled",
        ),
        # Счёт уже оплачен — повторно не выдаётся
        (
            "confirm",
            {"transId": "T-1"},
            {"счета": счёт("paid"), "транзакция": СВЕЖАЯ},
            ВХОД,
            (400, 10008),
            "paid",
            "created",
        ),
        ("confirm", {"transId": "T-9"}, {}, ВХОД, (400, 10014), "pending", None),
        (
            "reverse",
            {"transId": "T-1"},
            {"транзакция": СВЕЖАЯ},
            ВХОД,
            (200, "REVERSED"),
            "pending",
            "cancelled",
        ),
        (
            "reverse",
            {"transId": "T-1"},
            {"транзакция": ПРОВЕДЕНА},
            ВХОД,
            (400, 10017),
            "pending",
            "performed",
        ),
        (
            "reverse",
            {"transId": "T-1"},
            {"транзакция": ОТМЕНЕНА},
            ВХОД,
            (400, 10018),
            "pending",
            "cancelled",
        ),
        (
            "status",
            {"transId": "T-1"},
            {"транзакция": ПРОВЕДЕНА},
            ВХОД,
            (200, "CONFIRMED"),
            "pending",
            "performed",
        ),
        ("status", {"transId": "T-9"}, {}, ВХОД, (400, 10014), "pending", None),
        # Неизвестная операция
        ("nope", {"transId": "T-1"}, {}, ВХОД, (400, 10003), "pending", None),
    ],
)
def test_merchant(сайт, касса, операция, body, подготовка, вход, итог_, счёт_, транзакция_):
    итог = вызов(
        сайт,
        касса,
        f"/payments/uzum/callback/{операция}",
        тело(операция, **body),
        сброс(**подготовка),
        вход=вход,
    )
    данные = ответ(итог)
    база = итог["база"]
    код, статус = итог_

    assert итог["ответ"]["status"] == код
    assert данные["serviceId"] == body.get("serviceId", 777)

    if isinstance(статус, str):
        assert данные["status"] == статус
        assert данные["transId" if операция != "check" else "serviceId"]

        if статус in ВРЕМЯ_ИТОГА:
            assert isinstance(данные[ВРЕМЯ_ИТОГА[статус]], int)

        if операция != "check" or статус == "OK":
            assert данные["data"] == {
                "invoice": "SVD-000001",
                "description": "Счёт «SVD-000001» / тест",
                "amount": 150000,
            }
    else:
        assert (данные["status"], данные["errorCode"]) == ("FAILED", статус)

    assert [p[1] for p in база["payments"]] == [счёт_]
    assert [t[3] for t in база["transactions"]] == ([транзакция_] if транзакция_ else [])

    if счёт_ == "paid" and транзакция_ == "performed":
        # Оплачено через Uzum: у счёта провайдер и номер транзакции
        assert база["payments"][0][2:5] == (True, "uzum", "T-1")
    elif not (счёт_ == "paid" and операция == "check"):
        assert база["subscriptions"] == [] and база["wallet_log"] == []


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

    if что == "business":
        # Тариф на 30 дней с автопродлением
        assert база["subscriptions"] == [
            (
                _id("plans", "code = 'business'"),
                "active",
                "payment",
                True,
                "30 days",
                "Оплата счёта SVD-000001",
            )
        ]
        assert база["notifications"][0][1] == "Тариф «Business» активирован"
    else:
        # Пакет — 50 кредитов в кошелёк, с записью в журнале кошелька
        assert база["subscriptions"] == []
        assert база["wallets"] == [(50, 0, 0)]
        assert база["wallet_log"] == [("credits", 50, 50, "purchase", "App\\Models\\Payment", 1)]

    assert "Оплата счёта SVD-000001 зачислена" in [n[1] for n in база["notifications"]]
    assert len(база["events"]) == len(база["notifications"])


def test_подтверждение_с_промокодом_и_кошельком(сайт, касса):
    """Промокод счёта привязывается к подписке; кредиты прибавляются к прежним."""
    тариф = вызов(
        сайт,
        касса,
        "/payments/uzum/callback/confirm",
        тело("confirm", transId="T-1"),
        сброс(транзакция=СВЕЖАЯ, промокод=True),
    )
    assert тариф["база"]["promo"] == [("SALE", 1)]

    пакет = вызов(
        сайт,
        касса,
        "/payments/uzum/callback/confirm",
        тело("confirm", transId="T-1"),
        сброс(счета=счёт("pending", "pack"), транзакция=СВЕЖАЯ, кошелёк=True),
    )
    assert пакет["база"]["wallets"] == [(54, 1, 0)]
    assert пакет["база"]["wallet_log"][0][1:3] == (50, 54)


def test_merchant_выключен(сайт, касса):
    выключен = {"PAYMENTS_UZUM_ENABLED": "false"}
    итог = вызов(
        сайт,
        касса,
        "/payments/uzum/callback/check",
        тело("check", params=СЧЁТ),
        сброс(),
        env=выключен,
    )

    assert итог["ответ"]["status"] == 404


# ── Вебхук кассы ────────────────────────────────────────────────────

ПРИНЯТ = (200, {"status": "OK", "errorCode": None})
ОТКАЗ = (400, {"status": "FAILED", "errorCode": 99999})


@pytest.mark.parametrize(
    ("body", "режим", "подготовка", "итог_", "счёт_", "транзакция_"),
    [
        # Успех перепроверен у Uzum — счёт оплачен
        (
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            "completed",
            {},
            ПРИНЯТ,
            "paid",
            "performed",
        ),
        (
            {"orderId": "ORD-SVD-000001", "operationState": "success"},
            "completed",
            {"счета": (("SVD-000001", "pack", "pending"),)},
            ПРИНЯТ,
            "paid",
            "performed",
        ),
        # Uzum не подтвердил успех — отказ, ничего не записано
        (
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            "processing",
            {},
            ОТКАЗ,
            "pending",
            None,
        ),
        (
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            "отказ",
            {},
            ОТКАЗ,
            "pending",
            None,
        ),
        # Не успех — транзакция записана, счёт ждёт
        (
            {"orderId": "ORD-SVD-000001", "operationState": "FAIL"},
            "completed",
            {},
            ПРИНЯТ,
            "pending",
            "created",
        ),
        (
            {"orderId": "SVD-000001", "operationState": "PROCESSING"},
            "completed",
            {},
            ПРИНЯТ,
            "pending",
            "created",
        ),
        # Неизвестный заказ и пустые поля
        (
            {"orderId": "ORD-NOPE", "operationState": "FAIL"},
            "completed",
            {},
            ОТКАЗ,
            "pending",
            None,
        ),
        ({"orderId": "", "operationState": "SUCCESS"}, "completed", {}, ОТКАЗ, "pending", None),
        ({"operationState": "SUCCESS"}, "completed", {}, ОТКАЗ, "pending", None),
        # Счёт уже оплачен — второй раз не выдаётся
        (
            {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
            "completed",
            {"счета": (("SVD-000001", "business", "paid"),)},
            ПРИНЯТ,
            "paid",
            "performed",
        ),
    ],
)
def test_вебхук(сайт, касса, body, режим, подготовка, итог_, счёт_, транзакция_):
    касса.режим = режим
    итог = вызов(сайт, касса, "/payments/uzum/callback", body, сброс(**подготовка), вход=None)
    база = итог["база"]

    assert (итог["ответ"]["status"], ответ(итог)) == итог_
    assert [p[1] for p in база["payments"]] == [счёт_]
    assert [t[3] for t in база["transactions"]] == ([транзакция_] if транзакция_ else [])

    if транзакция_:
        # Номер транзакции — номер заказа Uzum, тело вебхука — в payload
        assert база["transactions"][0][2] == body["orderId"]
        assert json.loads(база["transactions"][0][6]) == body

    # Тариф или кредиты — только если счёт оплачен этим вебхуком
    уже_оплачен = any(статус == "paid" for _, _, статус in подготовка.get("счета", ()))
    assert bool(база["subscriptions"] or база["wallet_log"]) is (
        счёт_ == "paid" and not уже_оплачен
    )


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

    итог = вызов(
        сайт,
        касса,
        "/payments/uzum/callback",
        {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
        подготовка,
        вход=None,
    )
    база = итог["база"]

    assert (итог["ответ"]["status"], ответ(итог)) == ПРИНЯТ
    assert [t[3] for t in база["transactions"]] == ["performed"]
    assert база["subscriptions"] == [] and база["notifications"] == []


def test_вебхук_чужой_адрес(сайт, касса):
    итог = вызов(
        сайт,
        касса,
        "/payments/uzum/callback",
        {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
        сброс(),
        вход=None,
        env={"PAYMENTS_UZUM_CALLBACK_IPS": "10.0.0.1,10.0.0.2"},
    )

    # Адрес не из белого списка — отказ, ничего не записано
    assert (итог["ответ"]["status"], ответ(итог)) == ОТКАЗ
    assert итог["база"]["transactions"] == []
    assert итог["база"]["payments"][0][1] == "pending"


@pytest.mark.parametrize("provider", ["payme", "click"])
def test_вебхук_другой_провайдер(сайт, касса, provider):
    итог = вызов(
        сайт,
        касса,
        f"/payments/{provider}/callback",
        {"orderId": "ORD-SVD-000001", "operationState": "SUCCESS"},
        сброс(),
        вход=None,
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"]["transactions"] == []
