"""
Тарифы на Django (этап 3).

Цены из базы, сумовая — своя или по курсу ЦБ с округлением до тысяч
(половина — вверх, как round() у PHP). Курс Django читает из файлового
кэша (формат Laravel, как на боевом), поэтому проверки работают с
CACHE_STORE=file, а курс в кэш кладут сами.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from savdex import laravel_cache

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, из_django, открыть, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}


#: Ключи файлового кэша, которые трогают проверки
КУРСЫ, ЗАПАСНЫЕ = "cbu.rates", "cbu.rates.last"
СЧЁТЧИК = "pricing-promo:127.0.0.1"


def забыть(*ключи: str) -> None:
    """Cache::forget в файловом кэше."""
    for ключ in ключи:
        laravel_cache.file_path(ключ).unlink(missing_ok=True)


def курсы() -> None:
    # 150 $ × 12 650 = 1 897,5 тыс. — половина: PHP округляет вверх
    laravel_cache.put(КУРСЫ, {"USD": 12650.0, "EUR": 13790.25}, 86400)


def очистить_кэш() -> None:
    забыть(КУРСЫ, ЗАПАСНЫЕ, СЧЁТЧИК, f"{СЧЁТЧИК}:timer")


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
    # Своя сумовая цена, дробная долларовая и выключенный тариф
    sql("update plans set price_uzs = 499000 where code = 'flash'")
    sql("update plans set price_usd = 19.99 where code = 'business'")
    sql("update plans set is_active = false where code = 'vip'")
    очистить_кэш()
    курсы()

    try:
        with адрес() as root:
            yield root
    finally:
        очистить_кэш()


def тарифы(сайт: str, path: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    д = открыть(сайт, path, headers=headers, env=ФАЙЛОВЫЙ)

    assert д["status"] == 200
    стр = страница(д["body"])
    assert стр["component"] == "Pricing"

    return стр


@pytest.mark.parametrize(
    ("path", "язык"),
    [("/pricing", "ru"), ("/uz/pricing", "uz"), ("/en/pricing", "en"), ("/zh/pricing", "zh")],
)
def test_тарифы(сайт, path, язык):
    стр = тарифы(сайт, path)
    plans = {p["code"]: p for p in стр["props"]["plans"]}

    assert стр["props"]["locale"] == язык
    assert list(plans) == ["free", "flash", "business", "premium"]
    assert plans["flash"]["price_uzs"] == 499000
    assert plans["premium"]["price_uzs"] == 1_898_000
    assert plans["business"]["price_usd"] == 19.99
    # 19.99 × 12 650 = 252 873,5 → 253 тыс.
    assert plans["business"]["price_uzs"] == 253_000


def test_переход_inertia(сайт):
    версия = тарифы(сайт, "/pricing")["version"]
    д = открыть(
        сайт,
        "/en/pricing",
        headers={"X-Inertia": "true", "X-Inertia-Version": версия},
        env=ФАЙЛОВЫЙ,
    )

    # Ответ перехода — JSON страницы, без вёрстки
    assert д["status"] == 200
    assert д["headers"]["x-inertia"] == "true"
    assert д["headers"]["content-type"].startswith("application/json")
    стр = страница(д["body"])
    assert (стр["component"], стр["url"], стр["props"]["locale"]) == (
        "Pricing",
        "/en/pricing",
        "en",
    )

    # Устаревшая версия сборки — 409 и полный переход
    д = открыть(
        сайт,
        "/en/pricing",
        headers={"X-Inertia": "true", "X-Inertia-Version": "old"},
        env=ФАЙЛОВЫЙ,
    )
    # (адрес — без языкового префикса: его срезает LocalizeUrl, язык — в сессии)
    assert д["status"] == 409
    assert д["headers"]["x-inertia-location"] == сайт + "/pricing"


def test_курс_из_запасной_таблицы(сайт):
    """Основной таблицы нет — Django берёт последнюю удачную, к ЦБ не ходит."""
    забыть(КУРСЫ)
    laravel_cache.put(ЗАПАСНЫЕ, {"USD": 12000.0}, 30 * 86400)

    try:
        plans = {p["code"]: p for p in тарифы(сайт, "/pricing")["props"]["plans"]}
        assert plans["premium"]["price_uzs"] == 1_800_000

        # Ни основной, ни запасной — запасной курс CurrencyRate::DEFAULT_USD
        забыть(ЗАПАСНЫЕ)
        plans = {p["code"]: p for p in тарифы(сайт, "/pricing")["props"]["plans"]}
        assert plans["premium"]["price_uzs"] == 1_920_000
    finally:
        курсы()


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
    """RateLimiter::clear('pricing-promo:<IP>') и свежие курсы."""
    забыть(СЧЁТЧИК, f"{СЧЁТЧИК}:timer")
    курсы()


СКИДКА_30 = {"code": "SALE-30", "plan_code": "business", "discount_percent": 30, "days": None}


@pytest.mark.parametrize(
    ("promo", "код", "цена", "ошибка"),
    [
        # 253 000 × 0,7; доллары — 19,99 × 0,7
        ("SALE-30", СКИДКА_30, ("business", 13.99, 177100), None),
        # « sale—30 », как его кодирует браузер: регистр, пробелы и тире — неважны
        ("%20sale%E2%80%9430%20", СКИДКА_30, ("business", 13.99, 177100), None),
        (
            "free_14",
            {"code": "FREE-14", "plan_code": "premium", "discount_percent": None, "days": 14},
            ("premium", 0, 0),
            None,
        ),
        ("FREE-0", None, None, "Промокод выпущен с ошибкой: срок доступа не задан."),
        ("ZERO", None, None, "Промокод выпущен с ошибкой: размер скидки не задан."),
        ("USED", None, None, "Этот промокод уже активирован."),
        ("OLD", None, None, "Срок действия промокода истёк."),
        ("OFF", None, None, "Промокод отключён."),
        ("GONE", None, None, "Тариф по этому промокоду больше не выдаётся."),
        ("NOPE", None, None, "Такого промокода нет."),
        (
            "FLASH-15",
            {"code": "FLASH-15", "plan_code": "flash", "discount_percent": 15, "days": None},
            # Своя сумовая цена: 499 000 × 0,85
            ("flash", 34, 424150),
            None,
        ),
        ("", None, None, None),
        ("%20", None, None, None),
    ],
)
def test_промокод(сайт, promo, код, цена, ошибка):
    _коды()
    _сброс_счётчика()
    props = тарифы(сайт, f"/pricing?promo={promo}")["props"]
    со_скидкой = {
        p["code"]: (p["promo_price"]["price_usd"], p["promo_price"]["price_uzs"])
        for p in props["plans"]
        if p.get("promo_price")
    }

    assert props["promo"] == код
    assert со_скидкой == ({цена[0]: цена[1:]} if цена else {})

    if ошибка is None:
        assert props["promoError"] is None
    else:
        assert props["promoError"].startswith(ошибка), props["promoError"]


def test_промокод_массивом(сайт):
    """?promo[]=… — (string) массива у PHP: страница 500, как была у Laravel."""
    д = из_django(сайт, "/pricing?promo[]=x", env=ФАЙЛОВЫЙ)

    assert д["status"] == 500


def test_промокод_десять_проверок_в_час(сайт):
    _коды()
    _сброс_счётчика()

    # Десять проверок в час на адрес — одиннадцатая отклоняется, даже верный код
    for _ in range(10):
        props = тарифы(сайт, "/pricing?promo=NOPE")["props"]
        assert props["promo"] is None and props["promoError"]

    props = тарифы(сайт, "/pricing?promo=SALE-30")["props"]

    assert props["promo"] is None
    assert props["promoError"] == "Слишком много попыток ввести промокод. Попробуйте через час."
    # Без промокода страница счётчик не трогает
    assert тарифы(сайт, "/pricing")["props"]["promoError"] is None
