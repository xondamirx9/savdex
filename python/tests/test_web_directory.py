"""
«Страны» и «Партнёры» на Django (этап 3).

Страны: работающие и запланированные, порядок по полю sort и названию
по правилам языка (ICU), витрина до 12 компаний на страну. Партнёры:
счётчики генеральных, обычных и мультипартнёров, страница каждого вида,
тип компании из справочника или правовая форма, город и страна на языке
посетителя.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

import pytest

from .factories import компания, объявления
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как один сидер Laravel (GeoSeeder).
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


ГЕО = ("countries", "country_translations", "cities", "city_translations")


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники(*ГЕО)

    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(kz,)] = sql("select id from countries where code = 'kz'")
    [(city,)] = sql("select id from cities where country_id = %s order by id limit 1", [uz])

    for i in range(1, 15):
        компания(country_id=uz, city_id=city, rating=i % 5, verification_level=i % 3)

    компания(
        country_id=kz, city_id=None, type=None, legal_form="freelancer",
        partner_tier="general", partner_sort=2,
    )  # fmt: skip
    компания(
        country_id=kz, city_id=None, type=None, legal_form="legal",
        partner_tier="general", partner_sort=1,
    )  # fmt: skip
    компания(country_id=uz, city_id=city, partner_tier="partner", rating=4.5)
    компания(country_id=uz, city_id=city, partner_tier="multi")
    компания(country_id=uz, city_id=None, status="blocked", partner_tier="partner")
    объявления(3)
    # Одинаковый sort у трёх стран — порядок решает название по правилам языка
    sql("update countries set sort = 5 where code in ('tr', 'cn', 'ru')")

    with адрес() as root:
        yield root


@pytest.mark.parametrize(
    ("path", "узбекистан", "порядок"),
    [
        ("/countries", "Узбекистан", ["cn", "ru", "tr"]),
        ("/uz/countries", "Oʻzbekiston", ["ru", "tr", "cn"]),
        ("/en/countries", "Uzbekistan", ["cn", "ru", "tr"]),
        # По правилам языка: пиньинь (é, tǔ, zhōng), турецкая Ç — после C
        ("/zh/countries", "乌兹别克斯坦", ["ru", "tr", "cn"]),
        ("/tr/countries", "Özbekistan", ["cn", "ru", "tr"]),
    ],
)
def test_страны(сайт, path, узбекистан, порядок):
    д = открыть(сайт, path)
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200 and стр["component"] == "Countries"
    assert props["countries"] and props["planned"]
    assert all(len(c["items"]) <= 12 for c in props["countries"])

    # Работают Узбекистан (sort 0) и Казахстан; заблокированная не в счёт
    uz, kz = props["countries"]
    assert (uz["code"], uz["name"], uz["companies"], len(uz["items"])) == ("uz", узбекистан, 19, 12)
    assert (kz["code"], kz["companies"], len(kz["items"])) == ("kz", 2, 2)

    # Одинаковый sort — по названию на языке посетителя
    коды = [c["code"] for c in props["planned"]]
    assert коды[:2] == ["kg", "tj"]
    assert коды[2:5] == порядок


@pytest.mark.parametrize("path", ["/partners", "/en/partners", "/zh/partners"])
def test_партнёры(сайт, path):
    д = открыть(сайт, path)
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200 and стр["component"] == "Partners"
    # Заблокированный партнёр не считается
    assert props["tiers"] == [
        {"slug": "general", "count": 2},
        {"slug": "regular", "count": 1},
        {"slug": "multi", "count": 1},
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/partners/general",
        "/partners/regular",
        "/partners/multi",
        "/en/partners/general",
        "/zh/partners/multi",
    ],
)
def test_страница_вида_партнёров(сайт, path):
    д = открыть(сайт, path)
    вид = path.rsplit("/", 1)[1]
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200 and стр["component"] == "PartnersTier"
    assert props["tier"] == вид
    assert len(props["others"]) == 2 and вид not in props["others"]
    assert len(props["partners"]) == {"general": 2, "regular": 1, "multi": 1}[вид]

    if path == "/partners/general":
        # По partner_sort; тип — правовая форма, если нет типа из справочника
        assert [(p["type_label"], p["city"], p["country"]) for p in props["partners"]] == [
            (None, None, "Казахстан"),
            ("Фрилансер", None, "Казахстан"),
        ]
    elif path == "/zh/partners/multi":
        assert (props["partners"][0]["city"], props["partners"][0]["country"]) == (
            "塔什干",
            "乌兹别克斯坦",
        )
