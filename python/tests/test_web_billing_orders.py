"""
Этап 7, шаг 53: заказ, промокод и оплата счёта онлайн на Django
неотличимы от Laravel.

Заказ: без компании — ошибка; проверка ввода; незакрытый счёт на то же
самое — предупреждение или сразу оплата; счёт с номером из id и
уведомлением; при включённой кассе — уход на форму Uzum, отказ кассы
оставляет счёт. Промокод: бесплатный период (новая подписка, прежние
истекают, кошелёк на период) и скидка (счёт на остаток, полный счёт на
тот же тариф отменяется); все отказы — на поле или во флеш. Оплата
счёта: только свой неоплаченный, касса выключена — предупреждение.

Касса — поддельный сервер Uzum: обе стороны регистрируют в нём платёж,
и запросы к нему тоже сверяются. У администратора — строки журнала.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

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
    sql("update plans set price_uzs = 499000 where code = 'flash'")
    sql("update plans set price_uzs = 1000 where code = 'business'")
    sql(
        "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, is_active, "
        "created_at, updated_at) values ('m', 'Средний', 50, 30, 350000, 1, true, now(), now())"
    )
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        БЕЗ_ПЕРЕВОДА,
    )
    # Второй сотрудник компании: уведомление о тарифе — каждому
    учётка("colleague@savdex.uz", company_id=_id("companies", "slug = 'mine'"))

    with laravel(**БЕЗ_ПЕРЕВОДА) as root:
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


def _сверить_кассу(касса: Касса, до: int) -> list[dict[str, Any]]:
    """Запросы к кассе: первая половина — Django, вторая — Laravel."""
    новые = касса.запросы[до:]
    assert len(новые) % 2 == 0, новые
    half = len(новые) // 2

    assert новые[:half] == новые[half:], json.dumps(новые, ensure_ascii=False)

    return новые[:half]


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


# ── Заказ без кассы ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "plan", "id": "PLAN:business"},
        {"kind": "plan", "id": "PLAN:free"},
        {"kind": "credits", "id": "PACK"},
        {"kind": "plan", "id": 999999},
        {"kind": "credits", "id": 999999},
        {"kind": "other", "id": 1},
        {"kind": "plan", "id": "abc"},
        {},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_заказ(сайт, body, admin):
    body = dict(body)

    if isinstance(body.get("id"), str) and body["id"].startswith("PLAN:"):
        body["id"] = _plan(body["id"][5:])
    elif body.get("id") == "PACK":
        body["id"] = _id("credit_packs", "code = 'm'")

    итог = заказать(сайт, body, сброс(), uid=владелец(admin))

    if body.get("kind") == "plan" and body.get("id") == _plan("business"):
        assert итог["база"]["payments"][0][5] == "SVD-000001"
        assert итог["база"]["notifications"]


@pytest.mark.parametrize("счёт", ["business", "pack"])
def test_заказ_повторно(сайт, счёт):
    body = (
        {"kind": "plan", "id": _plan("business")}
        if счёт == "business"
        else {"kind": "credits", "id": _id("credit_packs", "code = 'm'")}
    )
    итог = заказать(сайт, body, сброс(счёт=счёт))

    assert len(итог["база"]["payments"]) == 1


def test_заказ_без_компании(сайт):
    uid = учётка("nocompany@savdex.uz", email_verified_at="2026-01-01 00:00:00")
    заказать(сайт, {"kind": "plan", "id": _plan("business")}, сброс(), uid=uid)


def test_заказ_без_подтверждённой_почты(сайт):
    итог = заказать(
        сайт, {"kind": "plan", "id": _plan("business")}, сброс(), uid=владелец(verified=False)
    )

    assert not итог["база"]["payments"]


# ── Заказ с кассой ──────────────────────────────────────────────────


@pytest.mark.parametrize("режим", ["ok", "вложенная", "отказ", "без_ссылки", "http"])
@pytest.mark.parametrize("admin", [False, True])
def test_заказ_онлайн(сайт, касса, режим, admin):
    касса.режим = режим
    env = онлайн(касса)

    with laravel(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до = len(касса.запросы)
        итог = заказать(
            root,
            {"kind": "plan", "id": _plan("business")},
            сброс(),
            uid=владелец(admin),
            env=env,
        )

    запросы = _сверить_кассу(касса, до)
    assert запросы and запросы[0]["path"] == "/api/v1/payment/register"

    if режим == "ok":
        assert итог["ответ"]["status"] == 409
        assert итог["база"]["payments"][0][9:11] == ("uzum", "ORD-SVD-000001")


def test_заказ_онлайн_с_корзиной_и_языком(сайт, касса):
    касса.режим = "ok"
    env = онлайн(
        касса,
        PAYMENTS_UZUM_SPIC="10305008002000000",
        PAYMENTS_UZUM_PACKAGE_CODE="1234",
        PAYMENTS_UZUM_TIN="301234567",
    )

    with laravel(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до = len(касса.запросы)
        отправить(
            root,
            "/uz/cabinet/billing/order",
            сброс(),
            снимок,
            uid=владелец(),
            body={"kind": "credits", "id": _id("credit_packs", "code = 'm'")},
            headers=inertia(),
            env=env,
        )

    [запрос] = _сверить_кассу(касса, до)
    assert запрос["headers"]["Content-Language"] == "uz-UZ"
    assert запрос["body"]["merchantParams"]["cart"]["items"][0]["receiptParams"]["TIN"]


def test_повторный_заказ_уводит_на_оплату(сайт, касса):
    касса.режим = "ok"
    env = онлайн(касса)

    with laravel(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до = len(касса.запросы)
        итог = заказать(
            root, {"kind": "plan", "id": _plan("business")}, сброс(счёт="business"), env=env
        )

    assert _сверить_кассу(касса, до)
    assert итог["база"]["payments"][0][10] == "ORD-SVD-000900"


# ── Оплата счёта ────────────────────────────────────────────────────


@pytest.mark.parametrize("онлайн_", [False, True])
@pytest.mark.parametrize("какой", ["свой", "чужой", "нет"])
def test_оплата_счёта(сайт, касса, онлайн_, какой):
    касса.режим = "ok"
    env = онлайн(касса) if онлайн_ else {}

    with laravel(**БЕЗ_ПЕРЕВОДА, **env) as root:
        сброс(счёт="business")()
        номер = _id("payments", "number = 'SVD-000900'")

        if какой == "чужой":
            sql("update payments set company_id = (select id from companies where slug = 'other')")
        elif какой == "нет":
            номер = 999999

        def подготовка() -> None:
            сброс(счёт="business", касса=None)()

            if какой == "чужой":
                sql(
                    "update payments set company_id = "
                    "(select id from companies where slug = 'other')"
                )

        до = len(касса.запросы)
        отправить(
            root,
            f"/cabinet/billing/invoice/{номер}/pay",
            подготовка,
            снимок,
            uid=владелец(),
            headers=inertia(),
            env=env,
        )

    _сверить_кассу(касса, до)


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


@pytest.mark.parametrize(
    ("code", "подготовка"),
    [
        # Бесплатный период: новой компании, с кошельком и без
        (" free-30 ", {"промокоды": (("FREE-30", "business", "30"),)}),
        ("free_30", {"промокоды": (("FREE-30", "business", "30"),), "кошелёк": True}),
        ("FREE-0", {"промокоды": (("FREE-0", "business", "0"),)}),
        ("FREE-30", {"промокоды": (("FREE-30", "business", "30"),), "оплачено": True}),
        ("FREE-30", {"промокоды": (("FREE-30", "business", "30"),), "подписка": "flash"}),
        # Скидка: счёт на остаток, полный счёт на тот же тариф — отменить
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),)}),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),), "счёт": "flash"}),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),), "подписка": "flash"}),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20"),), "подписка": "business"}),
        ("SALE-0", {"промокоды": (("SALE-0", "flash", "-0"),)}),
        ("FREE-PLAN", {"промокоды": (("FREE-PLAN", "free", "-50"),)}),
        # Свой захваченный скидочный: к его счёту или новый счёт
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20", "used"),), "счёт": "flash:SALE-20"}),
        ("SALE-20", {"промокоды": (("SALE-20", "flash", "-20", "used"),)}),
        (
            "SALE-20",
            {"промокоды": (("SALE-20", "flash", "-20", "used", "linked"),), "подписка": "flash"},
        ),
        # Отказы
        ("NOPE", {}),
        ("   ", {}),
        (None, {}),
        ("X" * 33, {}),
        ("USED", {"промокоды": (("USED", "flash", "30", "other"),)}),
        ("OLD", {"промокоды": (("OLD", "flash", "30", "old"),)}),
        ("OFF", {"промокоды": (("OFF", "flash", "30", "off"),)}),
        ("SECOND", {"промокоды": (("FIRST", "flash", "30", "used"), ("SECOND", "flash", "30"))}),
        ("VIP", {"промокоды": (("VIP", "vip", "30"),)}),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_промокод(сайт, code, подготовка, admin):
    if подготовка.get("промокоды") and any(p[1] == "vip" for p in подготовка["промокоды"]):
        sql("update plans set is_active = false where code = 'vip'")

    try:
        итог = промокод(сайт, code, сброс(**подготовка), admin=admin)
    finally:
        sql("update plans set is_active = true where code = 'vip'")

    база = итог["база"]

    if code == " free-30 ":
        [подписка] = база["subscriptions"]
        assert подписка[2] == "promo" and подписка[3] is False and подписка[4] == "30 days"
        assert база["promo"][0][4] == 1 and len(база["notifications"]) == 2
        assert bool(база["journal"]) is admin

    if code == "SALE-20" and подготовка.get("счёт") == "flash":
        старый, новый = база["payments"]
        assert старый[11] == "failed" and "SALE-20" in старый[12]
        assert новый[11] == "pending" and новый[7] == 399200

    if code == "SALE-20" and подготовка.get("счёт") == "flash:SALE-20":
        assert len(база["payments"]) == 1


def test_промокод_онлайн(сайт, касса):
    касса.режим = "ok"
    env = онлайн(касса)

    with laravel(**БЕЗ_ПЕРЕВОДА, **env) as root:
        до = len(касса.запросы)
        итог = промокод(
            root,
            "SALE-20",
            сброс(промокоды=(("SALE-20", "flash", "-20"),)),
            env=env,
            path="/en/cabinet/billing/promo",
        )

    [запрос] = _сверить_кассу(касса, до)
    assert запрос["body"]["amount"] == 399200 * 100
    assert итог["база"]["payments"][0][10] == "ORD-SVD-000001"


def test_промокод_без_компании(сайт):
    uid = учётка("nocompany2@savdex.uz", email_verified_at="2026-01-01 00:00:00")
    промокод(сайт, "FREE-30", сброс(), uid=uid)
