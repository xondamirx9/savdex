"""
Тарифы на Django неотличимы от Laravel (этап 3).

Цены из базы, сумовая — своя или по курсу ЦБ с округлением до тысяч
(половина — вверх, как round() у PHP). Курс Django читает из файлового
кэша Laravel — того же, что на боевом, поэтому обе стороны здесь
работают с CACHE_STORE=file, а курс в кэш кладёт сам Laravel.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, из_django, сверить, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}


def кэш(code: str) -> None:
    php(code, ФАЙЛОВЫЙ)


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
    # Своя сумовая цена, дробная долларовая и выключенный тариф
    sql("update plans set price_uzs = 499000 where code = 'flash'")
    sql("update plans set price_usd = 19.99 where code = 'business'")
    sql("update plans set is_active = false where code = 'vip'")
    очистить_кэш()
    # 150 $ × 12 650 = 1 897,5 тыс. — половина: PHP округляет вверх
    кэш("Cache::put('cbu.rates', ['USD' => 12650.0, 'EUR' => 13790.25], now()->addDay());")

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()


@pytest.mark.parametrize("path", ["/pricing", "/uz/pricing", "/en/pricing", "/zh/pricing"])
def test_тарифы(сайт, path):
    д, _ = сверить(сайт, path, env=ФАЙЛОВЫЙ)
    plans = {p["code"]: p for p in страница(д["body"])["props"]["plans"]}

    assert "vip" not in plans
    assert plans["flash"]["price_uzs"] == 499000
    assert plans["premium"]["price_uzs"] == 1_898_000
    assert plans["business"]["price_usd"] == 19.99


def test_переход_inertia(сайт):
    версия = страница(из_django(сайт, "/pricing", env=ФАЙЛОВЫЙ)["body"])["version"]

    сверить(
        сайт,
        "/en/pricing",
        headers={"X-Inertia": "true", "X-Inertia-Version": версия},
        env=ФАЙЛОВЫЙ,
    )


def test_курс_из_запасной_таблицы(сайт):
    """
    Основной таблицы нет — Django берёт последнюю удачную, к ЦБ не ходит.

    Laravel в этом случае сначала сходил бы в ЦБ, поэтому сверки с ним
    здесь нет: проверяется только Django.
    """
    кэш(
        "Cache::forget('cbu.rates');"
        "Cache::put('cbu.rates.last', ['USD' => 12000.0], now()->addMonth());"
    )

    try:
        д = из_django(сайт, "/pricing", env=ФАЙЛОВЫЙ)
        plans = {p["code"]: p for p in страница(д["body"])["props"]["plans"]}
        assert plans["premium"]["price_uzs"] == 1_800_000

        # Ни основной, ни запасной — запасной курс CurrencyRate::DEFAULT_USD
        кэш("Cache::forget('cbu.rates.last');")
        д = из_django(сайт, "/pricing", env=ФАЙЛОВЫЙ)
        plans = {p["code"]: p for p in страница(д["body"])["props"]["plans"]}
        assert plans["premium"]["price_uzs"] == 1_920_000
    finally:
        кэш("Cache::put('cbu.rates', ['USD' => 12650.0, 'EUR' => 13790.25], now()->addDay());")


# ── Промокод на витрине (шаг 70) ────────────────────────────────────


def _коды() -> None:
    sql("delete from promo_codes")
    план = {c: i for c, i in sql("select code, id from plans")}

    # (код, тариф, дней, скидка, погашен, истёк, включён)
    for код, тариф, дней, скидка, погашен, истёк, включён in (
        ("SALE-30", "business", 0, 30, False, False, True),
        ("FREE-14", "premium", 14, None, False, False, True),
        ("FREE-0", "premium", 0, None, False, False, True),
        ("ZERO", "business", 0, 0, False, False, True),
        ("USED", "business", 0, 30, True, False, True),
        ("OLD", "business", 0, 30, False, True, True),
        ("OFF", "business", 0, 30, False, False, False),
        ("GONE", "vip", 0, 30, False, False, True),
        ("FLASH-15", "flash", 0, 15, False, False, True),
    ):  # fmt: skip
        sql(
            "insert into promo_codes (code, plan_id, days, discount_percent, used_at, "
            "expires_at, is_active, created_at, updated_at) values "
            "(%s, %s, %s, %s, %s, %s, %s, now(), now())",
            [
                код, план[тариф], дней, скидка,
                "2026-01-01 00:00:00" if погашен else None,
                "2026-01-01 00:00:00" if истёк else None, включён,
            ],
        )  # fmt: skip


def _сброс_счётчика() -> None:
    кэш(
        "RateLimiter::clear('pricing-promo:127.0.0.1');"
        "Cache::put('cbu.rates', ['USD' => 12650.0, 'EUR' => 13790.25], now()->addDay());"
    )


@pytest.mark.parametrize(
    "promo",
    [
        "SALE-30",
        "%20sale%E2%80%9430%20",  # « sale—30 », как его кодирует браузер
        "free_14",
        "FREE-0",
        "ZERO",
        "USED",
        "OLD",
        "OFF",
        "GONE",
        "NOPE",
        "FLASH-15",
        "",
        "%20",
    ],
)
def test_промокод(сайт, promo):
    _коды()
    _сброс_счётчика()
    д, _ = сверить(сайт, f"/pricing?promo={promo}", env=ФАЙЛОВЫЙ, перед=_сброс_счётчика)
    props = страница(д["body"])["props"]

    if promo == "SALE-30":
        assert props["promo"] == {
            "code": "SALE-30",
            "plan_code": "business",
            "discount_percent": 30,
            "days": None,
        }
        business = next(p for p in props["plans"] if p["code"] == "business")
        assert business["promo_price"]["price_usd"] == 13.99
    elif promo in ("USED", "NOPE"):
        assert props["promo"] is None and props["promoError"]


def test_промокод_массивом(сайт):
    """?promo[]=… — (string) массива у PHP: страница 500 у обеих сторон."""
    from .web_site import из_laravel

    ответы = [
        сторона(сайт, "/pricing?promo[]=x", env=ФАЙЛОВЫЙ)
        if сторона is из_django
        else сторона(сайт, "/pricing?promo[]=x")
        for сторона in (из_django, из_laravel)
    ]

    assert [о["status"] for о in ответы] == [500, 500]


def test_промокод_десять_проверок_в_час(сайт):
    _коды()
    _сброс_счётчика()

    # Счётчик общий: пять проверок Django и пять Laravel — одиннадцатая отклоняется
    for _ in range(5):
        сверить(сайт, "/pricing?promo=NOPE", env=ФАЙЛОВЫЙ)

    д, _ = сверить(сайт, "/pricing?promo=SALE-30", env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]

    assert props["promo"] is None and props["promoError"]
