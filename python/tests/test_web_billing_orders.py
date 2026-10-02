"""
Этап 7, шаг 53: заказ, промокод и оплата счёта онлайн на Django.

Заказ: без компании — ошибка; проверка ввода; незакрытый счёт на то же
самое — предупреждение или сразу оплата; счёт с номером из id и
уведомлением; при включённой кассе — уход на форму Uzum, отказ кассы
оставляет счёт. Промокод: бесплатный период (новая подписка, прежние
истекают, кошелёк на период) и скидка (счёт на остаток, полный счёт на
тот же тариф отменяется); все отказы — на поле или во флеш. Оплата
счёта: только свой неоплаченный, касса выключена — предупреждение.

Касса — поддельный сервер Uzum: сайт регистрирует в нём платёж, и
запросы к нему тоже проверяются. У администратора — строки журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from .factories import компания
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база

БЕЗ_ПЕРЕВОДА = {"MACHINE_TRANSLATION_ENABLED": "false"}


class Касса:
    """Поддельный Uzum: запоминает запросы, отвечает по заданному режиму."""

    def __init__(self) -> None:
        self.режим = "ok"
        self.запросы: list[dict[str, Any]] = []
        касса = self

        class Обработчик(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                длина = int(self.headers.get("Content-Length") or 0)
                тело = json.loads(self.rfile.read(длина) or b"{}")
                касса.запросы.append(
                    {
                        "path": self.path,
                        "body": тело,
                        "headers": {
                            k: self.headers.get(k)
                            for k in ("X-Terminal-Id", "X-API-Key", "Content-Language")
                        },
                    }
                )
                status, ответ = касса.ответ(тело)
                данные = json.dumps(ответ).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(данные)))
                self.end_headers()
                self.wfile.write(данные)

            def log_message(self, *args: Any) -> None:
                pass

        self.сервер = ThreadingHTTPServer(("127.0.0.1", 0), Обработчик)
        threading.Thread(target=self.сервер.serve_forever, daemon=True).start()
        self.адрес = f"http://127.0.0.1:{self.сервер.server_address[1]}"

    def ответ(self, тело: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        заказ = "ORD-" + str(тело.get("orderNumber"))

        if self.режим == "http":
            return 500, {}

        if self.режим == "отказ":
            return 200, {"errorCode": 3045, "message": "Cart required"}

        if self.режим == "без_ссылки":
            return 200, {"errorCode": 0, "result": {"orderId": заказ}}

        # getOrderStatus: статус заказа в поле, которое выбрал Uzum
        if self.режим in ("completed", "processing"):
            return 200, {
                "errorCode": 0,
                "result": {"orderId": тело.get("orderId"), "orderStatus": self.режим.upper()},
            }

        if self.режим == "вложенная":
            return 200, {
                "errorCode": 0,
                "result": {"orderId": заказ, "links": {"form": "https://pay.example/" + заказ}},
            }

        return 200, {
            "errorCode": 0,
            "result": {"orderId": заказ, "paymentRedirectUrl": "https://pay.example/" + заказ},
        }


@pytest.fixture(scope="module")
def касса() -> Iterator[Касса]:
    касса = Касса()
    yield касса
    касса.сервер.shutdown()


def онлайн(касса: Касса, **extra: str) -> dict[str, str]:
    return {
        "PAYMENTS_UZUM_ENABLED": "true",
        "PAYMENTS_UZUM_CHECKOUT_ENABLED": "true",
        "PAYMENTS_UZUM_BASE_URL": касса.адрес + "/",
        "PAYMENTS_UZUM_TERMINAL_ID": "TERM-1",
        "PAYMENTS_UZUM_SECRET_KEY": "secret-key-1",
        "PAYMENTS_UZUM_RETURN_URL": "https://savdex.uz/cabinet/billing",
        **extra,
    }


def тарифы() -> None:
    """Тарифы из снимка savdex/bootstrap/seeds.json — как PlanSeeder."""
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        "seeds.seed(data={k: v if k == 'plans' else [] for k, v in data.items()})"
    )
    subprocess.run(
        [sys.executable, "-c", код],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            # Справочники заводит владелец базы, как миграции
            "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"],
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
        },
        capture_output=True,
        check=True,
    )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    тарифы()
    sql("update plans set price_uzs = 499000 where code = 'flash'")
    sql("update plans set price_uzs = 1000 where code = 'business'")
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    компания(slug="mine")
    компания(slug="other")
    # Второй сотрудник компании: уведомление о тарифе — каждому
    учётка("colleague@savdex.uz", company_id=_id("companies", "slug = 'mine'"))

    with адрес(**БЕЗ_ПЕРЕВОДА) as root:
        yield root


def _id(table: str, where: str) -> int:
    return int(sql(f"select id from {table} where {where}")[0][0])


def владелец(admin: bool = False, verified: bool = True) -> int:
    return учётка(
        "owner@savdex.uz",
        company_id=_id("companies", "slug = 'mine'"),
        is_admin=admin,
        email_verified_at="2026-01-01 00:00:00" if verified else None,
    )


def _plan(code: str) -> int:
    return _id("plans", f"code = '{code}'")


def сброс(
    *,
    подписка: str | None = None,
    счёт: str | None = None,
    промокоды: tuple[tuple[str, ...], ...] = (),
    оплачено: bool = False,
    кошелёк: bool = False,
    касса: Касса | None = None,
) -> Callable[[], None]:
    """
    промокоды — (код, тариф, дни или «-процент», пометки): «used» —
    захвачен своей компанией, «other» — чужой, «off» — выключен,
    «old» — просрочен, «linked» — уже связан с подпиской.
    """

    def run() -> None:
        sql(
            "truncate payment_transactions, payments, promo_codes, payment_methods, "
            "subscriptions, wallets, wallet_transactions, user_notifications, activity_events, "
            "admin_actions restart identity cascade"
        )
        sql("update users set locale = 'ru'")

        if касса is not None:
            касса.запросы.clear()

        mine = _id("companies", "slug = 'mine'")
        other = _id("companies", "slug = 'other'")

        if подписка is not None:
            sql(
                "insert into subscriptions (company_id, plan_id, status, source, auto_renew, "
                "started_at, ends_at, created_at, updated_at) values (%s, %s, 'active', "
                "'payment', true, now() - interval '5 days', now() + interval '25 days', "
                "now() - interval '5 days', now() - interval '5 days')",
                [mine, _plan(подписка)],
            )

        if кошелёк:
            sql(
                "insert into wallets (company_id, credits, promo_units, "
                "contacts_used_this_period, created_at, updated_at) values "
                "(%s, 3, 2, 5, now() - interval '5 days', now() - interval '5 days')",
                [mine],
            )

        if оплачено:
            sql(
                "insert into payments (company_id, purpose, description, amount, status, "
                "number, paid_at, created_at, updated_at) values (%s, 'credits', 'Старое', "
                "1000, 'paid', 'OLD-1', now(), now() - interval '9 days', "
                "now() - interval '9 days')",
                [mine],
            )

        for code, plan, срок, *пометки in промокоды:
            скидка = срок.startswith("-")
            sql(
                "insert into promo_codes (code, plan_id, days, discount_percent, is_active, "
                "expires_at, used_at, used_by_company_id, subscription_id, created_at, "
                "updated_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "now() - interval '1 day', now() - interval '1 day')",
                [
                    code,
                    _plan(plan),
                    0 if скидка else int(срок),
                    int(срок[1:]) if скидка else None,
                    "off" not in пометки,
                    "2020-01-01 00:00:00" if "old" in пометки else None,
                    "2026-09-01 00:00:00" if {"used", "other"} & set(пометки) else None,
                    mine if "used" in пометки else other if "other" in пометки else None,
                    None,
                ],
            )

            if "linked" in пометки:
                sql(
                    "update promo_codes set subscription_id = (select max(id) from "
                    "subscriptions) where code = %s",
                    [code],
                )

        if счёт is not None:
            код = счёт.split(":")[1] if ":" in счёт else None
            sql(
                "insert into payments (company_id, purpose, plan_id, credit_pack_id, "
                "promo_code_id, description, amount, status, number, provider, created_at, "
                "updated_at) values (%s, %s, %s, %s, (select id from promo_codes where code = %s), "
                "'Тариф', 1000, 'pending', 'SVD-000900', 'invoice', now() - interval '1 day', "
                "now() - interval '1 day')",
                [
                    mine,
                    "credits" if счёт.startswith("pack") else "subscription",
                    None if счёт.startswith("pack") else _plan(счёт.split(":")[0]),
                    _id("credit_packs", "code = 'm'") if счёт.startswith("pack") else None,
                    код,
                ],
            )

    return run


def снимок() -> Any:
    return {
        "payments": sql(
            "select company_id, purpose, plan_id, credit_pack_id, promo_code_id, number, "
            "description, amount, currency, provider, external_id, status, admin_note, "
            "subscription_id from payments order by id"
        ),
        "subscriptions": sql(
            "select plan_id, status, source, auto_renew, (ends_at - started_at)::text, "
            "cancelled_at is not null, granted_by, grant_reason from subscriptions order by id"
        ),
        "wallets": sql(
            "select credits, promo_units, contacts_used_this_period, "
            "round(extract(epoch from period_resets_at - now()) / 3600) from wallets order by id"
        ),
        "promo": sql(
            "select code, used_at is not null, used_by_company_id, used_by_user_id, "
            "subscription_id from promo_codes order by id"
        ),
        "notifications": sql(
            "select user_id, company_id, type, title, body, tone, url from user_notifications "
            "order by id"
        ),
        "events": sql("select company_id, type, tone, message, url from activity_events"),
        "journal": sql(
            "select action, section, subject_type, subject_id, subject_label, "
            "regexp_replace(changes::text, '\\d{4}-\\d\\d-\\d\\d[ T][0-9:.]+Z?', 'T', 'g') "
            "from admin_actions order by id"
        ),
    }


def запросы_кассы(касса: Касса, до: int) -> list[dict[str, Any]]:
    """Запросы к кассе после отметки до."""
    return касса.запросы[до:]


def заказать(сайт: str, body: Any, подготовка: Callable[[], None], **kw: Any) -> dict[str, Any]:
    return отправить(
        сайт,
        "/cabinet/billing/order",
        подготовка,
        снимок,
        uid=kw.pop("uid", None) or владелец(),
        body=body,
        headers=kw.pop("headers", inertia()),
        **kw,
    )


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return json.loads(итог["сессия"]["payload"])


def ошибка_поля(итог: dict[str, Any]) -> dict[str, list[str]]:
    """Ошибки проверки ввода в сессии: поле → сообщения."""
    return сессия(итог).get("errors", {}).get("default", {}).get("messages", {})


def счета(база: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Счета коротко: (назначение, номер, сумма, касса, заказ кассы, статус)."""
    return [(p[1], p[5], p[7], p[9], p[10], p[11]) for p in база["payments"]]


def действия(база: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Журнал коротко: (действие, раздел, номер записи) и правка разобранной."""
    return [(j[0], j[1], j[3], json.loads(j[5])) for j in база["journal"]]


def владельцу(база: dict[str, Any]) -> list[tuple[str, str]]:
    """Уведомления владельцу (заголовок, текст)."""
    uid = владелец()

    return [(n[3], n[4]) for n in база["notifications"] if n[0] == uid]


def до(дней: int) -> str:
    return (datetime.now(ZoneInfo("Asia/Tashkent")) + timedelta(days=дней)).strftime("%d.%m.%Y")


СФОРМИРОВАН = (
    "Счёт {n} на {сумма} сум сформирован. Реквизиты — ниже, доступ откроется после зачисления."
)
ОПЛАТИТЕ = ". Оплатите в течение 14 дней — доступ откроется после зачисления."
ЖДЁТ = "Счёт SVD-000900 на это уже выставлен и ждёт оплаты"
НЕДОСТУПНА = (
    "Онлайн-оплата сейчас недоступна. Счёт SVD-000001 выставлен — оплатите по реквизитам "
    "ниже, доступ откроется после зачисления."
)


# ── Заказ без кассы ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "ждём"),
    [
        # Счёт: (назначение, описание, сумма)
        (
            {"kind": "plan", "id": "PLAN:business"},
            ("subscription", "Тариф «Business» на 30 дн.", 1000),
        ),
        # Бесплатный тариф заказывается так же — счётом на 0 сум
        ({"kind": "plan", "id": "PLAN:free"}, ("subscription", "Тариф «Free» на 30 дн.", 0)),
        (
            {"kind": "credits", "id": "PACK"},
            ("credits", "Пакет «Средний»: 50 раскрытий контактов", 350000),
        ),
        ({"kind": "plan", "id": 999999}, 404),
        ({"kind": "credits", "id": 999999}, 404),
        ({"kind": "other", "id": 1}, {"kind"}),
        ({"kind": "plan", "id": "abc"}, {"id"}),
        ({}, {"kind", "id"}),
    ],
)  # fmt: skip
@pytest.mark.parametrize("admin", [False, True])
def test_заказ(сайт, body, ждём, admin):
    body = dict(body)

    if isinstance(body.get("id"), str) and body["id"].startswith("PLAN:"):
        body["id"] = _plan(body["id"][5:])
    elif body.get("id") == "PACK":
        body["id"] = _id("credit_packs", "code = 'm'")

    итог = заказать(сайт, body, сброс(), uid=владелец(admin))
    база = итог["база"]

    if ждём == 404:
        assert итог["ответ"]["status"] == 404
        assert база["payments"] == []
        return

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(ждём, set):
        assert set(ошибка_поля(итог)) == ждём
        assert база["payments"] == база["notifications"] == []
        return

    назначение, описание, сумма = ждём
    сумма_текст = f"{сумма:,}".replace(",", " ")

    # Номер счёта — из id; уведомление владельцу
    assert счета(база) == [(назначение, "SVD-000001", сумма, "invoice", None, "pending")]
    assert база["payments"][0][6] == описание
    assert сессия(итог)["success"] == СФОРМИРОВАН.format(n="SVD-000001", сумма=сумма_текст)
    # «…на 30 дн.» уже кончается точкой — второй перед «Оплатите» нет
    уведомление = описание.removesuffix(".") + ОПЛАТИТЕ
    assert владельцу(база) == [("Счёт SVD-000001 сформирован", уведомление)]
    assert [(n[2], n[5], n[6]) for n in база["notifications"]] == [
        ("billing", "info", "/cabinet/billing")
    ]

    if admin:
        assert [d[:3] for d in действия(база)] == [
            ("created", "payments", 1),
            ("updated", "payments", 1),
        ]
        assert действия(база)[1][3] == {"after": {"number": "SVD-000001"}}
    else:
        assert база["journal"] == []


@pytest.mark.parametrize("счёт", ["business", "pack"])
def test_заказ_повторно(сайт, счёт):
    body = (
        {"kind": "plan", "id": _plan("business")}
        if счёт == "business"
        else {"kind": "credits", "id": _id("credit_packs", "code = 'm'")}
    )
    итог = заказать(сайт, body, сброс(счёт=счёт))

    # Незакрытый счёт на то же — предупреждение, второго счёта нет
    assert сессия(итог)["warning"] == ЖДЁТ
    assert [p[5] for p in итог["база"]["payments"]] == ["SVD-000900"]
    assert итог["база"]["notifications"] == []


def test_заказ_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz", email_verified_at="2026-01-01 00:00:00")
    итог = заказать(сайт, {"kind": "plan", "id": _plan("business")}, сброс(), uid=uid)

    assert сессия(итог)["error"] == "Сначала заполните данные компании — счёт выставляется на неё"
    assert итог["база"]["payments"] == []


def test_заказ_без_подтверждённой_почты(сайт):
    итог = заказать(
        сайт, {"kind": "plan", "id": _plan("business")}, сброс(), uid=владелец(verified=False)
    )

    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert not итог["база"]["payments"]


# ── Заказ с кассой ──────────────────────────────────────────────────


#: Регистрация заказа в кассе: сумма в тийинах, номер счёта, адреса возврата
РЕГИСТРАЦИЯ = {
    "amount": 1000 * 100,
    "clientId": "1",
    "currency": 860,
    "paymentDetails": "Тариф «Business» на 30 дн.",
    "orderNumber": "SVD-000001",
    "sessionTimeoutSecs": 1800,
    "viewType": "REDIRECT",
    "successUrl": "https://savdex.uz/cabinet/billing",
    "failureUrl": "https://savdex.uz/cabinet/billing",
    "paymentParams": {"operationType": "PAYMENT", "payType": "ONE_STEP"},
}


@pytest.mark.parametrize("режим", ["ok", "вложенная", "отказ", "без_ссылки", "http"])
@pytest.mark.parametrize("admin", [False, True])
def test_заказ_онлайн(сайт, касса, режим, admin):
    касса.режим = режим
    env = онлайн(касса)

    with адрес(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до_ = len(касса.запросы)
        итог = заказать(
            root,
            {"kind": "plan", "id": _plan("business")},
            сброс(),
            uid=владелец(admin),
            env=env,
        )

    assert запросы_кассы(касса, до_) == [
        {
            "path": "/api/v1/payment/register",
            "body": {**РЕГИСТРАЦИЯ, "clientId": str(_id("companies", "slug = 'mine'"))},
            "headers": {
                "X-Terminal-Id": "TERM-1",
                "X-API-Key": "secret-key-1",
                "Content-Language": "ru-RU",
            },
        }
    ]
    база = итог["база"]

    if режим in ("ok", "вложенная"):
        # Уход на форму кассы (ссылка — в поле или вложенная)
        assert итог["ответ"]["status"] == 409
        assert (
            итог["ответ"]["headers"]["x-inertia-location"] == "https://pay.example/ORD-SVD-000001"
        )
        assert счета(база) == [
            ("subscription", "SVD-000001", 1000, "uzum", "ORD-SVD-000001", "pending")
        ]
    else:
        # Отказ кассы: счёт остаётся, оплатить можно по реквизитам
        assert итог["ответ"]["status"] == 302
        assert сессия(итог)["warning"] == НЕДОСТУПНА
        assert счета(база) == [("subscription", "SVD-000001", 1000, "invoice", None, "pending")]

    assert len(база["notifications"]) == 1

    if admin and режим in ("ok", "вложенная"):
        assert [d[3] for d in действия(база)[2:]] == [
            {"after": {"external_id": "ORD-SVD-000001"}},
            {"before": {"provider": "invoice"}, "after": {"provider": "uzum"}},
        ]
    elif admin:
        assert len(база["journal"]) == 2
    else:
        assert база["journal"] == []


def test_заказ_онлайн_с_корзиной_и_языком(сайт, касса):
    касса.режим = "ok"
    env = онлайн(
        касса,
        PAYMENTS_UZUM_SPIC="10305008002000000",
        PAYMENTS_UZUM_PACKAGE_CODE="1234",
        PAYMENTS_UZUM_TIN="301234567",
    )

    with адрес(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до_ = len(касса.запросы)
        итог = отправить(
            root,
            "/uz/cabinet/billing/order",
            сброс(),
            снимок,
            uid=владелец(),
            body={"kind": "credits", "id": _id("credit_packs", "code = 'm'")},
            headers=inertia(),
            env=env,
        )

    [запрос] = запросы_кассы(касса, до_)
    pack = _id("credit_packs", "code = 'm'")
    название = "«Средний» paketi: 50 ta kontakt ochish"

    # Язык кассы — язык страницы; описание счёта — тоже
    assert запрос["headers"]["Content-Language"] == "uz-UZ"
    assert запрос["body"]["paymentDetails"] == название
    assert запрос["body"]["merchantParams"] == {
        "cart": {
            "cartId": "SVD-000001",
            "receiptType": "PURCHASE",
            "total": 350000 * 100,
            "items": [
                {
                    "productId": f"credits-{pack}",
                    "title": название,
                    "quantity": 1,
                    "unitPrice": 350000 * 100,
                    "total": 350000 * 100,
                    "receiptParams": {
                        "spic": "10305008002000000",
                        "vatPercent": 12,
                        "packageCode": "1234",
                        "TIN": "301234567",
                    },
                }
            ],
        }
    }
    assert итог["база"]["payments"][0][6] == название


def test_повторный_заказ_уводит_на_оплату(сайт, касса):
    касса.режим = "ok"
    env = онлайн(касса)

    with адрес(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до_ = len(касса.запросы)
        итог = заказать(
            root, {"kind": "plan", "id": _plan("business")}, сброс(счёт="business"), env=env
        )

    # Ждущий счёт с кассой — сразу на оплату, нового счёта нет
    assert [(з["path"], з["body"]["orderNumber"]) for з in запросы_кассы(касса, до_)] == [
        ("/api/v1/payment/register", "SVD-000900")
    ]
    assert итог["ответ"]["headers"]["x-inertia-location"] == "https://pay.example/ORD-SVD-000900"
    assert счета(итог["база"]) == [
        ("subscription", "SVD-000900", 1000, "uzum", "ORD-SVD-000900", "pending")
    ]


# ── Оплата счёта ────────────────────────────────────────────────────


@pytest.mark.parametrize("онлайн_", [False, True])
@pytest.mark.parametrize("какой", ["свой", "чужой", "нет"])
def test_оплата_счёта(сайт, касса, онлайн_, какой):
    касса.режим = "ok"
    env = онлайн(касса) if онлайн_ else {}

    with адрес(**БЕЗ_ПЕРЕВОДА, **env) as root:
        сброс(счёт="business")()
        номер = _id("payments", "number = 'SVD-000900'")

        if какой == "нет":
            номер = 999999

        def подготовка() -> None:
            сброс(счёт="business", касса=None)()

            if какой == "чужой":
                sql(
                    "update payments set company_id = "
                    "(select id from companies where slug = 'other')"
                )

        до_ = len(касса.запросы)
        итог = отправить(
            root,
            f"/cabinet/billing/invoice/{номер}/pay",
            подготовка,
            снимок,
            uid=владелец(),
            headers=inertia(),
            env=env,
        )

    запросы = запросы_кассы(касса, до_)

    if какой != "свой":
        # Только свой счёт: чужой и несуществующий — 404, касса не тронута
        assert итог["ответ"]["status"] == 404
        assert запросы == []
        assert счета(итог["база"])[0][3:] == ("invoice", None, "pending")
    elif онлайн_:
        assert итог["ответ"]["status"] == 409
        assert (
            итог["ответ"]["headers"]["x-inertia-location"] == "https://pay.example/ORD-SVD-000900"
        )
        assert [з["body"]["orderNumber"] for з in запросы] == ["SVD-000900"]
        assert счета(итог["база"])[0][3:] == ("uzum", "ORD-SVD-000900", "pending")
    else:
        assert сессия(итог)["warning"] == (
            "Онлайн-оплата сейчас недоступна — оплатите счёт по реквизитам ниже"
        )
        assert запросы == []


# ── Промокод ────────────────────────────────────────────────────────


def промокод(сайт: str, code: Any, подготовка: Callable[[], None], **kw: Any) -> dict[str, Any]:
    return отправить(
        сайт,
        kw.pop("path", "/cabinet/billing/promo"),
        подготовка,
        снимок,
        uid=kw.pop("uid", None) or владелец(kw.pop("admin", False)),
        body={} if code is None else {"promo_code": code},
        headers=inertia(),
        **kw,
    )


ВЫДАН_С_ОШИБКОЙ = "Промокод выпущен с ошибкой: {}. Напишите в поддержку."
УЖЕ = "Этот промокод уже активирован."
СКИДКА = (
    "Промокод принят: скидка 20%. Счёт {n} на {сумма} сум выставлен — оплатите по реквизитам, "
    "тариф включится после зачисления."
)


@pytest.mark.parametrize(
    ("code", "подготовка", "ждём"),
    [
        # Бесплатный период: новой компании, с кошельком и без
        (" free-30 ", {"промокоды": (("FREE-30", "business", "30"),)}, "бесплатно"),
        (
            "free_30",
            {"промокоды": (("FREE-30", "business", "30"),), "кошелёк": True},
            "бесплатно",
        ),
        (
            "FREE-0",
            {"промокоды": (("FREE-0", "business", "0"),)},
            ("поле", ВЫДАН_С_ОШИБКОЙ.format("срок доступа не задан")),
        ),
        (
            "FREE-30",
            {"промокоды": (("FREE-30", "business", "30"),), "оплачено": True},
            ("поле", "Этот промокод действует только для компаний, которые ещё не "
             "оплачивали тариф."),
        ),
        (
            "FREE-30",
            {"промокоды": (("FREE-30", "business", "30"),), "подписка": "flash"},
            ("поле", "У вашей компании уже есть действующий тариф. Промокод можно активировать, "
             "когда он закончится."),
        ),
        # Скидка: счёт на остаток, полный счёт на тот же тариф — отменить
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),)}, "скидка"),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),), "счёт": "flash"}, "замена"),
        (
            "SALE-20",
            {"промокоды": (("SALE-20", "flash", "-20"),), "подписка": "flash"},
            ("поле", "Этот тариф у вашей компании уже действует. Активируйте промокод, когда "
             "текущий период закончится."),
        ),
        # Другой тариф действует — скидка на flash всё равно
        (
            "SALE-20",
            {"промокоды": (("SALE-20", "flash", "-20"),), "подписка": "business"},
            "скидка",
        ),
        (
            "SALE-0",
            {"промокоды": (("SALE-0", "flash", "-0"),)},
            ("поле", ВЫДАН_С_ОШИБКОЙ.format("размер скидки не задан")),
        ),
        (
            "FREE-PLAN",
            {"промокоды": (("FREE-PLAN", "free", "-50"),)},
            ("поле", ВЫДАН_С_ОШИБКОЙ.format("тариф по нему не продаётся")),
        ),
        # Свой захваченный скидочный: к его счёту или новый счёт
        (
            "SALE-20",
            {"промокоды": (("SALE-20", "flash", "-20", "used"),), "счёт": "flash:SALE-20"},
            "свой счёт",
        ),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20", "used"),)}, "скидка"),
        (
            "SALE-20",
            {"промокоды": (("SALE-20", "flash", "-20", "used", "linked"),), "подписка": "flash"},
            ("флеш", УЖЕ),
        ),
        # Отказы
        ("NOPE", {}, ("поле", "Такого промокода нет. Проверьте, правильно ли он набран.")),
        ("   ", {}, ("поле", "Введите промокод")),
        (None, {}, ("поле", "Введите промокод")),
        ("X" * 33, {}, ("поле", "Не длиннее 32 символов.")),
        ("USED", {"промокоды": (("USED", "flash", "30", "other"),)}, ("поле", УЖЕ)),
        (
            "OLD",
            {"промокоды": (("OLD", "flash", "30", "old"),)},
            ("поле", "Срок действия промокода истёк."),
        ),
        (
            "OFF",
            {"промокоды": (("OFF", "flash", "30", "off"),)},
            ("поле", "Промокод отключён. Напишите в поддержку, если получили его недавно."),
        ),
        (
            "SECOND",
            {"промокоды": (("FIRST", "flash", "30", "used"), ("SECOND", "flash", "30"))},
            ("флеш", "Ваша компания уже активировала промокод — второй раз акция не действует."),
        ),
        (
            "VIP",
            {"промокоды": (("VIP", "vip", "30"),)},
            ("поле", "Тариф по этому промокоду больше не выдаётся. Напишите в поддержку."),
        ),
    ],
)  # fmt: skip
@pytest.mark.parametrize("admin", [False, True])
def test_промокод(сайт, code, подготовка, ждём, admin):
    if подготовка.get("промокоды") and any(p[1] == "vip" for p in подготовка["промокоды"]):
        sql("update plans set is_active = false where code = 'vip'")

    try:
        итог = промокод(сайт, code, сброс(**подготовка), admin=admin)
    finally:
        sql("update plans set is_active = true where code = 'vip'")

    база = итог["база"]
    mine, uid = _id("companies", "slug = 'mine'"), владелец()
    flash, business = _plan("flash"), _plan("business")

    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(ждём, tuple):
        куда, текст = ждём

        if куда == "поле":
            assert ошибка_поля(итог) == {"promo_code": [текст]}
        else:
            assert сессия(итог)["error"] == текст

        # Ничего не выдано: ни подписки по коду, ни счёта, ни уведомлений
        assert all(s[2] != "promo" for s in база["subscriptions"])
        assert [p[5] for p in база["payments"]] == (["OLD-1"] if подготовка.get("оплачено") else [])
        assert база["notifications"] == база["journal"] == []
        return

    if ждём == "бесплатно":
        # Новая подписка по коду, кошелёк на период, код погашен
        assert база["subscriptions"] == [
            (business, "active", "promo", False, "30 days", False, uid, "Промокод FREE-30")
        ]
        assert база["wallets"] == (
            [(3, 2 + 50, 0, 720)] if подготовка.get("кошелёк") else [(0, 50, 0, 720)]
        )
        assert база["promo"] == [("FREE-30", True, mine, uid, 1)]
        assert сессия(итог)["success"] == (
            f"Промокод активирован: тариф «Business» бесплатно до {до(30)}."
        )
        # Уведомление — каждому сотруднику компании
        assert [(n[2], n[3], n[4]) for n in база["notifications"]] == [
            ("billing", "Тариф «Business» активирован", f"Действует до {до(30)}."),
        ] * 2
        assert len(база["events"]) == 1
        assert [d[:3] for d in действия(база)] == (
            [("created", "subscriptions", 1)] if admin else []
        )
        return

    if ждём == "свой счёт":
        # Свой счёт по этому коду уже есть — к нему и возвращаемся
        assert счета(база) == [("subscription", "SVD-000900", 1000, "invoice", None, "pending")]
        assert сессия(итог)["success"] == СКИДКА.format(n="SVD-000900", сумма="1 000")
        assert база["notifications"] == []
        return

    # Скидка 20% от 499 000 — счёт на 399 200; код захвачен компанией
    номер = "SVD-000002" if ждём == "замена" else "SVD-000001"
    новый = ("subscription", номер, 399200, "invoice", None, "pending")
    захватил = None if "used" in подготовка["промокоды"][0] else uid

    if ждём == "замена":
        старый = база["payments"][0]

        assert счета(база) == [
            ("subscription", "SVD-000900", 1000, "invoice", None, "failed"),
            новый,
        ]
        assert старый[12] == "Заменён счётом со скидкой по промокоду SALE-20"
    else:
        assert счета(база) == [новый]

    assert база["payments"][-1][2] == flash and база["payments"][-1][4] == 1
    assert база["promo"] == [("SALE-20", True, mine, захватил, None)]
    assert сессия(итог)["success"] == СКИДКА.format(n=номер, сумма="399 200")
    assert владельцу(база) == [
        (
            f"Счёт {номер} сформирован",
            "Тариф «Flash» на 30 дн. · промокод SALE-20, скидка 20%" + ОПЛАТИТЕ,
        )
    ]
    # Подписки по скидке нет, пока счёт не оплачен
    assert all(s[2] != "promo" for s in база["subscriptions"])


def test_промокод_онлайн(сайт, касса):
    касса.режим = "ok"
    env = онлайн(касса)

    with адрес(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до_ = len(касса.запросы)
        итог = промокод(
            root,
            "SALE-20",
            сброс(промокоды=(("SALE-20", "flash", "-20"),)),
            env=env,
            path="/en/cabinet/billing/promo",
        )

    [запрос] = запросы_кассы(касса, до_)

    # Счёт со скидкой — сразу на форму кассы
    assert запрос["body"]["amount"] == 399200 * 100
    # Так в протоколе Uzum: en-EN, а не en-US
    assert запрос["headers"]["Content-Language"] == "en-EN"
    assert итог["ответ"]["status"] == 409
    assert итог["ответ"]["headers"]["x-inertia-location"] == "https://pay.example/ORD-SVD-000001"
    assert итог["база"]["payments"][0][10] == "ORD-SVD-000001"


def test_промокод_без_компании(сайт):
    uid = учётка("nocompany2@savdex.uz", email_verified_at="2026-01-01 00:00:00")
    итог = промокод(сайт, "FREE-30", сброс(), uid=uid)

    assert ошибка_поля(итог) == {
        "promo_code": ["Сначала заполните данные компании — тариф выдаётся на неё"]
    }
    assert итог["база"]["subscriptions"] == []
