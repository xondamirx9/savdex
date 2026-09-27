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
