"""
Этап 4, шаг 7: каталог объявлений /catalog на Django.

Выдача: живые объявления активных компаний, на всех языках — и
загруженные из книги без перевода; поиск, тип, раздел с подразделами,
город, проверенные, с ценой; сортировки (подходящие — продвинутые
выше), постраничный вывод. И статистика: показы (listings, listing_stats)
с отсевом повторов в файловом кэше и поисковые запросы (search_hits).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest

from .factories import компания, объявление
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, гостевая, открыть, страница

pytestmark = нужна_база

#: Файловый кэш, как на боевом: курс ЦБ для цен в валюте языка, отсев
#: повторных показов и счётчик частоты живут в нём
ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: Ключи курса ЦБ в кэше (CurrencyRate)
КУРС = ("cbu.rates", "cbu.rates.last", "cbu.rate.usd.last")

#: Свой адрес посетителя: счётчик частоты в общем файловом кэше — только наш
IP = {"X-Forwarded-For": "198.51.100.47"}

ГЕО = ("countries", "country_translations", "cities", "city_translations")
РАЗДЕЛЫ = ("categories", "category_translations", "category_fields")


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (GeoSeeder, CategorySeeder,
    PromotionTypeSeeder). Как на свежей базе (fresh): типы продвижения
    заводятся только так.
    """
    код = (
        "import json, django; django.setup(); from savdex import seeds; "
        "data = json.loads(seeds.DATA.read_text(encoding='utf-8')); "
        f"only = {list(таблицы)!r}; "
        "seeds.seed(fresh=True, data={k: v if k in only else [] for k, v in data.items()})"
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


def файл_кэша(key: str):
    """FileStore::path: data/aa/bb/<sha1 ключа>."""
    digest = hashlib.sha1(key.encode()).hexdigest()

    return КОРЕНЬ / "storage/framework/cache/data" / digest[:2] / digest[2:4] / digest


def счётчик_частоты() -> None:
    """Счётчик throttle гостя с адресом IP — с нуля (ключ sha1(«|IP»))."""
    key = hashlib.sha1(f"|{IP['X-Forwarded-For']}".encode()).hexdigest()

    for name in (key, key + ":timer"):
        файл_кэша(name).unlink(missing_ok=True)


def курс() -> None:
    """Курс ЦБ — в кэш заранее: страница к ЦБ не ходит, цены в валюте языка известны."""
    from savdex import laravel_cache

    laravel_cache.put(
        "cbu.rates",
        {"USD": 12650.5, "CNY": 1760.25, "TRY": 305.1, "EUR": 13710.0, "RUB": 140.2, "KZT": 25.3},
        86400,
    )


#: Что завёл сайт(): номера объявлений, городов и разделов
ДАННЫЕ: dict[str, Any] = {}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники(*ГЕО, *РАЗДЕЛЫ, "promotion_types")

    # 26 живых (две страницы) у трёх компаний, импорт без перевода,
    # черновик, объявление заблокированной компании; продвижения
    [(uz,)] = sql("select id from countries where code = 'uz'")
    города = [
        r[0] for r in sql("select id from cities where country_id = %s order by id limit 2", [uz])
    ]
    [(раздел,)] = sql("select id from categories where parent_id is null order by sort, id limit 1")
    [(подраздел,)] = sql(
        "select id from categories where parent_id = %s order by sort, id limit 1", [раздел]
    )
    [(другой,)] = sql(
        "select id from categories where parent_id is null order by sort, id offset 1 limit 1"
    )
    компании_ = [компания(verification_level=i, city_id=города[i % 2]) for i in range(3)]
    начало = datetime(2026, 9, 20, 12)
    ids = [
        объявление(
            company_id=компании_[i % 3],
            type="supply" if i % 4 else "demand",
            title=("Цемент М400 " if i % 5 else "Sement M500 ") + str(i),
            category_id=[раздел, подраздел, другой][i % 3],
            city_id=города[i % 2],
            price=100_000 * (i % 7) if i % 6 else None,
            price_negotiable=i % 9 == 0,
            published_at=начало - timedelta(hours=i % 8),
        )
        for i in range(1, 27)
    ]
    # Загруженное из книги, без перевода: видно на всех языках
    объявление(
        source="import",
        title_i18n=None,
        title="Щебень фракция 5-20",
        company_id=компании_[0],
        published_at=начало - timedelta(days=10),
    )
    объявление(draft=True, company_id=компании_[0])
    объявление(company_id=компания(status="blocked"))

    типы = dict(sql("select code, id from promotion_types"))

    for lid, code in ((ids[20], "bump"), (ids[21], "highlight"), (ids[22], "urgent")):
        sql(
            "insert into promotions (listing_id, company_id, promotion_type_id, units_spent, "
            "status, starts_at, ends_at, active_key, created_at, updated_at) "
            "select id, company_id, %s, 1, 'active', now(), now() + interval '7 days', %s, "
            "now(), now() from listings where id = %s",
            [типы[code], f"{lid}:{типы[code]}", lid],
        )

    курс()
    счётчик_частоты()
    ДАННЫЕ.update(ids=ids, города=города, раздел=раздел, подраздел=подраздел, другой=другой)

    try:
        with адрес() as root:
            yield root
    finally:
        for key in КУРС:
            файл_кэша(key).unlink(missing_ok=True)

        счётчик_частоты()


def обнулить() -> None:
    """Статистика и счётчик частоты с нуля."""
    счётчик_частоты()
    sql("update listings set impressions_count = 0")
    sql("delete from listing_stats")
    sql("delete from search_hits")


def каталог(сайт: str, path: str, cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """Страница каталога со статистикой с нуля; сразу после ответа."""
    обнулить()
    д = открыть(сайт, path, cookies, IP, ФАЙЛОВЫЙ)
    assert д["status"] == 200, д["body"][:500]

    return страница(д["body"])


def заголовки(props: dict[str, Any]) -> list[str]:
    return [x["title"] for x in props["listings"]["data"]]


#: 26 живых и одно загруженное: 27; черновик и объявление заблокированной
#: компании — не в выдаче
@pytest.mark.parametrize(
    ("path", "total", "на_странице", "фильтры"),
    [
        ("/catalog", 27, 20, {}),
        ("/catalog?page=2", 27, 7, {}),
        ("/en/catalog", 27, 20, {}),
        ("/uz/catalog?page=2", 27, 7, {}),
        ("/catalog?sort=fresh", 27, 20, {"sort": "fresh"}),
        ("/catalog?sort=cheap&page=2", 27, 7, {"sort": "cheap"}),
        ("/catalog?sort=expensive", 27, 20, {"sort": "expensive"}),
        ("/catalog?sort=nonsense", 27, 20, {"sort": "relevant"}),
        # Спрос — каждое четвёртое: 4, 8 … 24
        ("/catalog?type=demand", 6, 6, {"type": "demand"}),
        # Проверена только третья компания: 2, 5 … 26 без спроса (8, 20)
        ("/catalog?type=supply&verified=1", 7, 7, {"type": "supply", "verified": True}),
        # Без цены (6, 12, 18, 24) и «договорная» (9) — нет
        ("/catalog?with_price=yes", 22, 20, {"with_price": True}),
        ("/catalog?city=abc", 27, 20, {"city": None}),
        # «Цемент» кириллицей — кроме каждого пятого (Sement M500)
        ("/catalog?q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82", 21, 20, {"q": "цемент"}),
        # Латиницей — все 26: поиск находит и кириллицу (обе графики), но не щебень
        ("/catalog?q=sement", 26, 20, {"q": "sement"}),
        ("/catalog?q=%20%20", 27, 20, {"q": ""}),
        # «0» — строка поиска (есть во всех «М400», «5-20»), а тип «0» — без отбора
        ("/zh/catalog?q=0&type=0", 27, 20, {"q": "0", "type": "0"}),
        ("/tr/catalog?q=%D0%BD%D0%B5%D1%82%D1%83", 0, 0, {"q": "нету"}),
    ],
)
def test_выдача(сайт, path, total, на_странице, фильтры):
    стр = каталог(сайт, path)
    props = стр["props"]

    assert стр["component"] == "catalog/Index"
    assert props["total"] == props["listings"]["total"] == total
    assert len(props["listings"]["data"]) == на_странице
    assert {k: props["filters"][k] for k in фильтры} == фильтры
    # Показы засчитаны ровно тому, что попало в выдачу
    assert sql("select coalesce(sum(impressions_count), 0) from listings")[0][0] == на_странице


def test_подходящие_продвинутые_выше(сайт):
    первая = каталог(сайт, "/catalog")["props"]["listings"]["data"]
    вторая = каталог(сайт, "/catalog?page=2")["props"]["listings"]["data"]

    # Поднятое (bump) и срочное (urgent) — первыми, дальше — по свежести
    assert [x["title"] for x in первая[:3]] == [
        "Цемент М400 21",
        "Цемент М400 23",
        "Цемент М400 24",
    ]
    assert [x["promoted"] for x in первая[:3]] == [True, True, False]
    # Выделение (highlight) в карточке видно, но выше не поднимает
    [выделенное] = [x for x in вторая if x["title"] == "Цемент М400 22"]
    assert выделенное["promoted"]


def test_цена_в_валюте_языка(сайт):
    """Курс ЦБ — из файлового кэша: 200 000 сум по 12 650,5 — 15,8 доллара."""
    карточки = {x["title"]: x for x in каталог(сайт, "/en/catalog")["props"]["listings"]["data"]}

    assert карточки["Цемент М400 23"]["converted"] == {"price": 15.8, "currency": "USD"}
    assert карточки["Цемент М400 8"]["converted"] == {"price": 7.9, "currency": "USD"}
    # Без цены и «договорная» — без пересчёта
    assert карточки["Цемент М400 24"]["converted"] is None
    assert карточки["Цемент М400 9"]["converted"] is None


def test_сортировки(сайт):
    свежие = заголовки(каталог(сайт, "/catalog?sort=fresh")["props"])
    дорогие = каталог(сайт, "/catalog?sort=expensive")["props"]["listings"]["data"]
    дешёвые = каталог(сайт, "/catalog?sort=cheap&page=2")["props"]["listings"]["data"]

    # Опубликованы в 12:00 — 8, 16, 24; при равенстве — новее номер
    assert свежие[:3] == ["Цемент М400 24", "Цемент М400 16", "Цемент М400 8"]
    assert [x["title"] for x in дорогие[:2]] == ["Sement M500 20", "Цемент М400 13"]
    цены = [x["price"] for x in дорогие]
    assert цены == sorted(цены, reverse=True)
    # Без цены — в конце и у «дешёвых»
    assert [x["price"] for x in дешёвые][-4:] == [None] * 4


def test_раздел_и_город(сайт):
    props = каталог(сайт, "/catalog")["props"]
    раздел = props["categories"][0]["id"]
    город = props["cities"][0]["id"]
    assert раздел == ДАННЫЕ["раздел"]

    props = каталог(сайт, f"/catalog?category={раздел}&city={город}")["props"]

    # Раздел — с подразделом (i % 3 = 0 и 1), город — свой у чётных и нечётных
    ожидаемо = [i for i in range(1, 27) if i % 3 != 2 and ДАННЫЕ["города"][i % 2] == город]
    assert props["filters"]["category"] == раздел
    assert props["filters"]["city"] == город
    assert props["total"] == len(ожидаемо)
    assert sorted(int(t.split()[-1]) for t in заголовки(props)) == ожидаемо


def статистика() -> tuple[object, ...]:
    return (
        sql("select id, impressions_count from listings where impressions_count > 0 order by id"),
        sql("select listing_id, impressions, views from listing_stats order by listing_id"),
        sql("select company_id, query, impressions from search_hits order by company_id"),
    )


def test_статистика_страницы(сайт):
    """Вторая страница: показ каждому из семи, строка дня; запроса нет — нет и search_hits."""
    props = каталог(сайт, "/catalog?page=2")["props"]
    показанные = sorted(x["id"] for x in props["listings"]["data"])
    объявления_, дни, запросы = статистика()

    assert объявления_ == [(i, 1) for i in показанные]
    assert дни == [(i, 1, 0) for i in показанные]
    assert запросы == []
    [(сегодня,)] = sql("select count(*) from listing_stats where date = current_date")
    assert сегодня == 7


def test_статистика_поиска(сайт):
    """Запрос — как его увидит компания: пробелы схлопнуты, строчными; по разу на компанию."""
    # «М400» — кириллицей, как в заголовках
    props = каталог(сайт, "/catalog?q=%20%D0%A6%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%20%20%D0%9C400")[
        "props"
    ]
    объявления_, _, запросы = статистика()

    assert props["total"] == 21
    assert len(объявления_) == 20
    показанные = [x["id"] for x in props["listings"]["data"]]
    компании_ = [
        r[0]
        for r in sql(
            "select distinct company_id from listings where id = any(%s) order by 1",
            [показанные],
        )
    ]
    assert запросы == [(c, "цемент м400", 1) for c in компании_]


def test_повтор_показа_отсеивает_кэш(сайт):
    """Одна сессия: показы засчитаны — повтор в течение получаса их не считает."""
    куки = гостевая(сайт)

    каталог(сайт, "/catalog", куки)
    assert sql("select sum(impressions_count) from listings")[0][0] == 20

    sql("update listings set impressions_count = 0")
    открыть(сайт, "/catalog", куки, IP, ФАЙЛОВЫЙ)
    assert sql("select sum(impressions_count) from listings")[0][0] == 0

    # Другая страница — другие объявления, их засчитывает
    открыть(сайт, "/catalog?page=2", куки, IP, ФАЙЛОВЫЙ)
    assert sql("select sum(impressions_count) from listings")[0][0] == 7
