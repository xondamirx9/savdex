"""
Этап 7, шаг 52: касса /cabinet/billing и печатный счёт на Django
неотличимы от Laravel.

Касса: тариф компании с ценой в сумах и долларах (по курсу из кэша
Laravel или своей сумовой), подписка с оставшимися днями, кошелёк,
карты, последние платежи с картой оплаты, тарифы и пакеты кредитов,
неоплаченные счета со сроком, реквизиты из настроек, выбранный тариф
(?plan=), включена ли онлайн-касса, можно ли ввести промокод.
Без компании — пустая касса.

Счёт: только свой, чужой и несуществующий — 404; у ожидающего — срок
и напоминание про номер в назначении платежа, у оплаченного — дата
оплаты.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file", "MACHINE_TRANSLATION_ENABLED": "false"}
КАССА = {"PAYMENTS_UZUM_ENABLED": "true", "PAYMENTS_UZUM_CHECKOUT_ENABLED": "true"}


def очистить_кэш() -> None:
    subprocess.run(
        ["php", "artisan", "cache:clear"],
        cwd=КОРЕНЬ,
        env={**ОКРУЖЕНИЕ, **ФАЙЛОВЫЙ},
        check=True,
        capture_output=True,
    )


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
    sql("update plans set price_usd = 19.99 where code = 'business'")
    sql("update plans set is_active = false where code = 'vip'")

    # Пакеты: по курсу, со своей сумовой ценой, выключенный
    for code, name, credits, usd, uzs, sort, active in (
        ("s", "Малый", 10, 7.5, None, 2, True),
        ("m", "Средний", 50, 30, 350000, 1, True),
        ("off", "Старый", 5, 1, None, 3, False),
    ):
        sql(
            "insert into credit_packs (code, name, credits, price_usd, price_uzs, sort, "
            "is_active, created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, now(), now())",
            [code, name, credits, usd, uzs, sort, active],
        )

    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'owner',"
        " 'legal_name' => 'ООО «Касса & Ко»', 'tin' => '301234567']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "$plan = App\\Models\\Plan::where('code', 'business')->first();"
        "$s = App\\Models\\Subscription::create(['company_id' => $c->id, 'plan_id' => $plan->id,"
        " 'status' => 'active', 'auto_renew' => true, 'started_at' => now()->subDays(10),"
        " 'ends_at' => now()->addDays(20)->addHours(5)]);"
        "App\\Models\\Wallet::create(['company_id' => $c->id, 'credits' => 12, 'promo_units' => 3,"
        " 'contacts_used_this_period' => 4, 'period_resets_at' => now()->addDays(9)]);"
        "$m1 = App\\Models\\PaymentMethod::create(['company_id' => $c->id, 'provider' => 'uzum',"
        " 'token' => 't1', 'brand' => 'Humo', 'last4' => '1234', 'expires' => '12/28',"
        " 'is_default' => true]);"
        "App\\Models\\PaymentMethod::create(['company_id' => $c->id, 'provider' => 'uzum',"
        " 'token' => 't2', 'brand' => null, 'last4' => '9876']);"
        "$m3 = App\\Models\\PaymentMethod::create(['company_id' => $o->id, 'provider' => 'uzum',"
        " 'token' => 't3', 'brand' => 'Visa', 'last4' => '5555']);"
        "foreach ([[$c, $m1, 'paid', 30, 29, 'SVX-1', 'Тариф «Бизнес»', 'UZS', 'uzum'],"
        " [$c, null, 'paid', 25, 20, 'SVX-2', 'Пакет кредитов', 'UZS', 'bank'],"
        " [$c, $m3, 'failed', 15, null, 'SVX-3', 'Тариф <b>Премиум</b>', 'UZS', null],"
        " [$c, null, 'pending', 6, null, 'SVX-4', 'Тариф «Флеш»', 'UZS', 'bank'],"
        " [$c, null, 'pending', 3, null, 'SVX-5', 'Кредиты в долларах', 'USD', null],"
        " [$c, null, 'refunded', 40, 39, 'SVX-6', 'Возврат', 'UZS', 'uzum'],"
        " [$o, null, 'pending', 2, null, 'SVX-7', 'Чужой счёт', 'UZS', 'bank']]"
        " as [$who, $m, $status, $ago, $paid, $num, $desc, $cur, $prov]) {"
        " $p = App\\Models\\Payment::forceCreate(['company_id' => $who->id,"
        " 'payment_method_id' => $m?->id, 'subscription_id' => null, 'purpose' => 'plan',"
        " 'description' => $desc, 'amount' => 1234567, 'currency' => $cur,"
        " 'provider' => $prov, 'status' => $status,"
        " 'paid_at' => $paid === null ? null : now()->subDays($paid), 'number' => $num]);"
        " $p->forceFill(['created_at' => now()->subDays($ago)->subHours(2)])->save(); }"
        "echo 'ok';",
        ФАЙЛОВЫЙ,
    )

    # Получатель — полное наименование; пустой счёт в реквизиты не идёт
    php(
        "App\\Models\\Setting::put('legal_full_name', 'ООО «SavdEx Market»');"
        "App\\Models\\Setting::put('legal_account', '');"
        "App\\Models\\Setting::put('legal_bank', 'АКБ <Капиталбанк>');"
        "echo 'ok';",
        ФАЙЛОВЫЙ,
    )

    очистить_кэш()
    php("Cache::put('cbu.rates', ['USD' => 12650.0], now()->addDay()); echo 'ok';", ФАЙЛОВЫЙ)

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()


def владелец(сайт: str) -> dict[str, str]:
    email = "owner@savdex.uz"

    if not sql("select 1 from users where email = %s", [email]):
        пользователь(email)
        sql(
            "update users set company_id = (select id from companies where slug = 'owner') "
            "where email = %s",
            [email],
        )

    sql("update users set locale = 'ru' where email = %s", [email])

    return войти(сайт, email)


def дни(props: dict[str, Any]) -> None:
    """Сколько дней до конца подписки — от мгновения ответа: сверяем до минуты."""
    подписка = props.get("subscription")

    if подписка and подписка.get("days_left") is not None:
        подписка["days_left"] = round(подписка["days_left"] * 1440)


def касса(сайт: str, path: str, куки: dict[str, str], env: dict[str, str] | None = None):
    return сверить(сайт, path, куки, env={**ФАЙЛОВЫЙ, **(env or {})}, чистка=дни)


# ── Касса ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/cabinet/billing",
        "/en/cabinet/billing",
        "/uz/cabinet/billing",
        "/cabinet/billing?plan=business",
        "/cabinet/billing?plan=",
    ],
)
def test_касса(сайт, path):
    д, _ = касса(сайт, path, владелец(сайт))
    props = страница(д["body"])["props"]

    if path != "/cabinet/billing":
        return

    assert props["plan"]["code"] == "business" and props["plan"]["price_usd"] == 19.99
    assert props["subscription"]["auto_renew"] is True
    assert props["wallet"]["credits"] == 12
    assert sorted(c["masked"] for c in props["cards"]) == ["Humo •••• 1234", "Карта •••• 9876"]
    # В истории только оплаченное и возвраты: отменённый SVX-3
    # и неоплаченные SVX-4/5 туда не попадают
    assert [p["status"] for p in props["payments"]] == ["paid", "paid", "refunded"]
    assert [p["method"] for p in props["payments"]] == ["Bank", "Uzum · Humo •••• 1234", "Uzum"]
    assert [p["number"] for p in props["invoices"]] == ["SVX-5", "SVX-4"]
    assert props["invoices"][0]["amount"] == "1 234 567 USD"
    packs = {p["name"]: p for p in props["packs"]}
    assert "Старый" not in packs and packs["Средний"]["price_uzs"] == 350000
    assert "vip" not in [p["code"] for p in props["plans"]]
    assert props["checkout"] is False and props["promoAllowed"] is True
    assert next(iter(props["requisites"].values())) == "ООО «SavdEx Market»"


def test_касса_онлайн(сайт):
    """Онлайн-касса включена у обеих сторон."""
    with laravel(**ФАЙЛОВЫЙ, **КАССА) as root:
        д, _ = касса(root, "/cabinet/billing", владелец(root), КАССА)

    assert страница(д["body"])["props"]["checkout"] is True


def test_касса_без_подписки_и_кошелька(сайт):
    """Бесплатный тариф: подписки нет, кошелька нет — нули."""
    sql(
        "update subscriptions set status = 'expired' "
        "where company_id = (select id from companies where slug = 'owner')"
    )
    sql("update wallets set company_id = (select id from companies where slug = 'other')")

    try:
        д, _ = касса(сайт, "/cabinet/billing", владелец(сайт))
    finally:
        sql(
            "update subscriptions set status = 'active' "
            "where company_id = (select id from companies where slug = 'owner')"
        )
        sql("update wallets set company_id = (select id from companies where slug = 'owner')")

    props = страница(д["body"])["props"]

    assert props["subscription"] is None and props["wallet"]["credits"] == 0


def test_промокод_использован(сайт):
    """Погашенный код на бесплатный период прячет форму промокода."""
    [(owner,)] = sql("select id from companies where slug = 'owner'")
    sql(
        "insert into promo_codes (code, plan_id, days, used_by_company_id, used_at, "
        "created_at, updated_at) select 'USED1', id, 30, %s, now(), now(), now() "
        "from plans where code = 'business'",
        [owner],
    )

    try:
        д, _ = касса(сайт, "/cabinet/billing", владелец(сайт))
    finally:
        sql("delete from promo_codes where code = 'USED1'")

    assert страница(д["body"])["props"]["promoAllowed"] is False


def test_без_компании(сайт):
    пользователь("nocompany@savdex.uz")
    д, _ = касса(сайт, "/cabinet/billing", войти(сайт, "nocompany@savdex.uz"))

    assert страница(д["body"])["props"]["plan"] is None


def test_гость_уходит_на_вход(сайт):
    д, _ = сверить(сайт, "/cabinet/billing", env=ФАЙЛОВЫЙ)

    assert д["status"] == 302


# ── Печатный счёт ───────────────────────────────────────────────────


def _счёт(number: str) -> int:
    return int(sql("select id from payments where number = %s", [number])[0][0])


def сверить_счёт(сайт: str, path: str, куки: dict[str, str]) -> dict[str, Any]:
    д = из_django(сайт, path, куки, env=ФАЙЛОВЫЙ)
    л = из_laravel(сайт, path, куки)

    assert д["status"] == л["status"], (д["status"], л["status"], д["body"][:500])

    if л["status"] == 200:
        assert д["body"] == л["body"], (д["body"][:3000], л["body"][:3000])
        assert д["headers"].get("content-type") == л["headers"].get("content-type")
    else:
        for header in ("location",):
            assert д["headers"].get(header) == л["headers"].get(header)

    return д


@pytest.mark.parametrize("number", ["SVX-1", "SVX-3", "SVX-4", "SVX-5", "SVX-6"])
def test_счёт(сайт, number):
    д = сверить_счёт(сайт, f"/cabinet/billing/invoice/{_счёт(number)}", владелец(сайт))

    assert д["status"] == 200 and number in д["body"]


def test_счёт_на_английском(сайт):
    сверить_счёт(сайт, f"/en/cabinet/billing/invoice/{_счёт('SVX-4')}", владелец(сайт))


@pytest.mark.parametrize("номер", ["чужой", "нет"])
def test_чужой_счёт(сайт, номер):
    payment = _счёт("SVX-7") if номер == "чужой" else 999999
    д = сверить_счёт(сайт, f"/cabinet/billing/invoice/{payment}", владелец(сайт))

    assert д["status"] == 404


def test_счёт_без_компании(сайт):
    пользователь("nocompany2@savdex.uz")
    д = сверить_счёт(
        сайт, f"/cabinet/billing/invoice/{_счёт('SVX-4')}", войти(сайт, "nocompany2@savdex.uz")
    )

    assert д["status"] == 404


def test_счёт_гостю(сайт):
    д = сверить_счёт(сайт, f"/cabinet/billing/invoice/{_счёт('SVX-4')}", {})

    assert д["status"] == 302
