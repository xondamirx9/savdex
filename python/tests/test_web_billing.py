"""
Этап 7, шаг 52: касса /cabinet/billing и печатный счёт на Django.

Касса: тариф компании с ценой в сумах и долларах (по курсу из кэша
Laravel или своей сумовой), подписка с оставшимися днями, кошелёк,
карты, последние платежи с картой оплаты, тарифы и пакеты кредитов,
неоплаченные счета со сроком, реквизиты из настроек, выбранный тариф
(?plan=), включена ли онлайн-касса, можно ли ввести промокод.
Без компании — пустая касса.

Счёт: только свой, чужой и несуществующий — 404; у ожидающего — срок
и напоминание про номер в назначении платежа, у оплаченного — дата
оплаты.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from savdex import laravel_cache

from .factories import компания
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file", "MACHINE_TRANSLATION_ENABLED": "false"}
КАССА = {"PAYMENTS_UZUM_ENABLED": "true", "PAYMENTS_UZUM_CHECKOUT_ENABLED": "true"}


#: Курсы ЦБ в файловом кэше (CurrencyRate) — на время проверок свои
КУРСЫ = "cbu.rates"


def очистить_кэш() -> None:
    laravel_cache.file_path(КУРСЫ).unlink(missing_ok=True)


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (PlanSeeder).
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"seeds.seed(data={{k: v if k in {list(таблицы)!r} else [] for k, v in data.items()}})"
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
    справочники("plans")
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

    c = компания(slug="owner", legal_name="ООО «Касса & Ко»", tin="301234567")
    o = компания(slug="other")
    sql(
        "insert into subscriptions (company_id, plan_id, status, auto_renew, started_at, ends_at, "
        "created_at, updated_at) select %s, id, 'active', true, now() - interval '10 days', "
        "now() + interval '20 days 5 hours', now(), now() from plans where code = 'business'",
        [c],
    )
    sql(
        "insert into wallets (company_id, credits, promo_units, contacts_used_this_period, "
        "period_resets_at, created_at, updated_at) "
        "values (%s, 12, 3, 4, now() + interval '9 days', now(), now())",
        [c],
    )
    карты = {}

    for company, token, brand, last4, expires, default in (
        (c, "t1", "Humo", "1234", "12/28", True),
        (c, "t2", None, "9876", None, False),
        (o, "t3", "Visa", "5555", None, False),
    ):
        [(карты[token],)] = sql(
            "insert into payment_methods (company_id, provider, token, brand, last4, expires, "
            "is_default, created_at, updated_at) values (%s, 'uzum', %s, %s, %s, %s, %s, now(), "
            "now()) returning id",
            [company, token, brand, last4, expires, default],
        )

    for who, card, status, ago, paid, number, description, currency, provider in (
        (c, "t1", "paid", 30, 29, "SVX-1", "Тариф «Бизнес»", "UZS", "uzum"),
        (c, None, "paid", 25, 20, "SVX-2", "Пакет кредитов", "UZS", "bank"),
        (c, "t3", "failed", 15, None, "SVX-3", "Тариф <b>Премиум</b>", "UZS", None),
        (c, None, "pending", 6, None, "SVX-4", "Тариф «Флеш»", "UZS", "bank"),
        (c, None, "pending", 3, None, "SVX-5", "Кредиты в долларах", "USD", None),
        (c, None, "refunded", 40, 39, "SVX-6", "Возврат", "UZS", "uzum"),
        (o, None, "pending", 2, None, "SVX-7", "Чужой счёт", "UZS", "bank"),
    ):
        sql(
            "insert into payments (company_id, payment_method_id, subscription_id, purpose, "
            "description, amount, currency, provider, status, paid_at, number, created_at, "
            "updated_at) values (%s, %s, null, 'plan', %s, 1234567, %s, %s, %s, "
            "now() - make_interval(days => %s), %s, "
            "now() - make_interval(days => %s) - interval '2 hours', now())",
            [
                who,
                карты.get(card),
                description,
                currency,
                provider,
                status,
                paid,
                number,
                ago,
            ],
        )

    # Получатель — полное наименование; пустой счёт в реквизиты не идёт
    for key, value in (
        ("legal_full_name", "ООО «SavdEx Market»"),
        ("legal_account", ""),
        ("legal_bank", "АКБ <Капиталбанк>"),
    ):
        sql("update settings set value = %s where key = %s", [json.dumps(value), key])

    очистить_кэш()
    laravel_cache.put(КУРСЫ, {"USD": 12650.0}, 86400)

    try:
        with адрес() as root:
            yield root
    finally:
        очистить_кэш()


def владелец(сайт: str) -> dict[str, str]:
    email = "owner@savdex.uz"
    found = sql("select id from users where email = %s", [email])
    uid = int(found[0][0]) if found else пользователь(email)
    sql(
        "update users set locale = 'ru', "
        "company_id = (select id from companies where slug = 'owner') where id = %s",
        [uid],
    )

    return вход(uid)


def касса(
    сайт: str, path: str, куки: dict[str, str], env: dict[str, str] | None = None
) -> dict[str, Any]:
    д = открыть(сайт, path, куки, env={**ФАЙЛОВЫЙ, **(env or {})})

    assert д["status"] == 200, д["status"]
    assert страница(д["body"])["component"] == "cabinet/Billing"

    return д


# ── Касса ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "язык", "выбран"),
    [
        ("/cabinet/billing", "ru", None),
        ("/en/cabinet/billing", "en", None),
        ("/uz/cabinet/billing", "uz", None),
        ("/cabinet/billing?plan=business", "ru", "business"),
        ("/cabinet/billing?plan=", "ru", None),
    ],
)
def test_касса(сайт, path, язык, выбран):
    д = касса(сайт, path, владелец(сайт))
    props = страница(д["body"])["props"]

    assert props["locale"] == язык
    assert props["selected"] == выбран
    assert props["plan"]["code"] == "business" and props["plan"]["price_usd"] == 19.99
    # Сумовой цены у пакета нет — по курсу из кэша (12 650), до тысяч:
    # 7.5 × 12 650 = 94 875 → 95 000; у «Среднего» своя сумовая цена
    packs = {p["name"]: p for p in props["packs"]}
    assert packs["Малый"]["price_uzs"] == 95000 and packs["Малый"]["per_credit"] == 9500
    assert packs["Средний"]["price_uzs"] == 350000
    plans = {p["code"]: p for p in props["plans"]}
    # Своя сумовая цена «Флеш» — в долларах по курсу: 499 000 / 12 650
    assert (plans["flash"]["price_uzs"], plans["flash"]["price_usd"]) == (499000, 39.4)
    assert plans["business"]["current"] is True
    assert props["subscription"]["auto_renew"] is True
    # Как ends_at->diffInDays(now()) у Carbon 3 — со знаком минус; страница
    # это поле не показывает
    assert 20 < abs(props["subscription"]["days_left"]) < 21
    assert props["wallet"]["credits"] == 12
    assert sorted(c["masked"] for c in props["cards"]) == ["Humo •••• 1234", "Карта •••• 9876"]
    # В истории только оплаченное и возвраты: отменённый SVX-3
    # и неоплаченные SVX-4/5 туда не попадают
    assert [p["status"] for p in props["payments"]] == ["paid", "paid", "refunded"]
    assert [p["method"] for p in props["payments"]] == ["Bank", "Uzum · Humo •••• 1234", "Uzum"]
    assert [p["number"] for p in props["invoices"]] == ["SVX-5", "SVX-4"]
    assert props["invoices"][0]["amount"] == "1 234 567 USD"
    assert "Старый" not in packs
    assert "vip" not in plans
    assert props["checkout"] is False and props["promoAllowed"] is True
    assert next(iter(props["requisites"].values())) == "ООО «SavdEx Market»"


def test_касса_онлайн(сайт):
    """Онлайн-касса включена."""
    д = касса(сайт, "/cabinet/billing", владелец(сайт), КАССА)

    assert страница(д["body"])["props"]["checkout"] is True


def test_касса_без_подписки_и_кошелька(сайт):
    """Бесплатный тариф: подписки нет, кошелька нет — нули."""
    sql(
        "update subscriptions set status = 'expired' "
        "where company_id = (select id from companies where slug = 'owner')"
    )
    sql("update wallets set company_id = (select id from companies where slug = 'other')")

    try:
        д = касса(сайт, "/cabinet/billing", владелец(сайт))
    finally:
        sql(
            "update subscriptions set status = 'active' "
            "where company_id = (select id from companies where slug = 'owner')"
        )
        sql("update wallets set company_id = (select id from companies where slug = 'owner')")

    props = страница(д["body"])["props"]

    assert props["subscription"] is None and props["wallet"]["credits"] == 0
    assert props["plan"]["code"] == "free"


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
        д = касса(сайт, "/cabinet/billing", владелец(сайт))
    finally:
        sql("delete from promo_codes where code = 'USED1'")

    assert страница(д["body"])["props"]["promoAllowed"] is False


def test_без_компании(сайт):
    д = касса(сайт, "/cabinet/billing", вход(пользователь("nocompany@savdex.uz")))
    props = страница(д["body"])["props"]

    assert props["plan"] is None and props["subscription"] is None
    assert props["payments"] == [] and props["invoices"] == [] and props["cards"] == []


def test_гость_уходит_на_вход(сайт):
    д = открыть(сайт, "/cabinet/billing", env=ФАЙЛОВЫЙ)

    assert д["status"] == 302
    assert д["headers"]["location"] == сайт + "/login"


# ── Печатный счёт ───────────────────────────────────────────────────


def _счёт(number: str) -> int:
    return int(sql("select id from payments where number = %s", [number])[0][0])


def счёт(сайт: str, path: str, куки: dict[str, str]) -> dict[str, Any]:
    return открыть(сайт, path, куки, env=ФАЙЛОВЫЙ)


@pytest.mark.parametrize("number", ["SVX-1", "SVX-3", "SVX-4", "SVX-5", "SVX-6"])
def test_счёт(сайт, number):
    д = счёт(сайт, f"/cabinet/billing/invoice/{_счёт(number)}", владелец(сайт))

    assert д["status"] == 200 and number in д["body"]
    assert д["headers"]["content-type"].startswith("text/html")
    # Плательщик и получатель; угловые скобки из настроек экранированы
    assert "ООО «Касса &amp; Ко»" in д["body"] and "301234567" in д["body"]
    assert "ООО «SavdEx Market»" in д["body"]
    assert "АКБ &lt;Капиталбанк&gt;" in д["body"]
    assert "<b>Премиум</b>" not in д["body"]


def test_счёт_на_английском(сайт):
    д = счёт(сайт, f"/en/cabinet/billing/invoice/{_счёт('SVX-4')}", владелец(сайт))

    # Счёт — документ на русском при любом языке сайта
    assert д["status"] == 200 and "<title>Счёт SVX-4 · SAVDEX</title>" in д["body"]


@pytest.mark.parametrize("номер", ["чужой", "нет"])
def test_чужой_счёт(сайт, номер):
    payment = _счёт("SVX-7") if номер == "чужой" else 999999
    д = счёт(сайт, f"/cabinet/billing/invoice/{payment}", владелец(сайт))

    assert д["status"] == 404


def test_счёт_без_компании(сайт):
    д = счёт(
        сайт,
        f"/cabinet/billing/invoice/{_счёт('SVX-4')}",
        вход(пользователь("nocompany2@savdex.uz")),
    )

    assert д["status"] == 404


def test_счёт_гостю(сайт):
    д = счёт(сайт, f"/cabinet/billing/invoice/{_счёт('SVX-4')}", {})

    assert д["status"] == 302
    assert д["headers"]["location"] == сайт + "/login"
