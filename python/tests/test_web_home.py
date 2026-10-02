"""
Главная на Django (этап 3).

Данные — справочники (снимок сидеров, savdex/seeds.py), задачи услуг
и компании с объявлениями из фабрик: витрина VIP с платным продвижением
и истёкшей подпиской, импортированное объявление без перевода, цены в
долларах, евро и «договорная», фотографии с уменьшенной копией и без,
ИП без типа компании, баннер с картинкой под язык, свой фон первого
экрана, скрытая секция и отзывы. Курс — из файлового кэша,
как на боевом.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from collections.abc import Iterator

import pytest

from savdex import laravel_cache

from .factories import Выражение, it_задача, компания, объявление, отзыв
from .pg_admin import PYTHON, КОРЕНЬ, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: PNG 3 × 2 — пропорция фона 1.5
КАДР = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAEUlEQVR4nGP4z8DwHwoYSGYCAKq9Jfr"
    "B8PoKAAAAAElFTkSuQmCC"
)

КУРСЫ = {"USD": 12650.0, "EUR": 13790.25, "CNY": 1755.4, "TRY": 380.12}


def справочники() -> None:
    """Свежая база, как db:seed: manage.py seed --fresh (savdex/seeds.py)."""
    subprocess.run(
        [sys.executable, "manage.py", "seed", "--fresh"],
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


def данные() -> None:
    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(kz,)] = sql("select id from countries where code = 'kz'")
    cities = [
        r[0] for r in sql("select id from cities where country_id = %s order by id limit 3", [uz])
    ]

    # Задачи услуг: IT (веб и приложения) впереди логистики
    for service in ("web", "web", "web", "mobile", "logistics", "logistics"):
        it_задача(service_type=service)

    companies = [
        компания(
            country_id=kz if i == 5 else uz,
            city_id=None if i == 5 else cities[i % 3],
            verification_level=i % 3,
            rating=3 + i * 0.3,
            legal_form="individual" if i == 4 else "legal",
            type=None if i == 4 else "importer",
            phone=f"+998 90 000 00 0{i}",
            email=f"c{i}@example.com" if i % 2 else None,
        )
        for i in range(6)
    ]

    for c in companies:
        for _ in range(3):
            объявление(company_id=c)

        объявление(company_id=c, type="demand")

    for n, (lid,) in enumerate(sql("select id from listings order by id limit 5")):
        sql(
            "insert into listing_images (listing_id, path, thumb_path, sort, created_at, "
            "updated_at) values (%s, %s, %s, 1, now(), now()), (%s, %s, null, 0, now(), now())",
            [
                lid,
                f"listings/{n}.jpg",
                None if n % 2 else f"listings/thumb-{n}.jpg",
                lid,
                f"listings/b{n}.jpg",
            ],
        )

    [(vip,)] = sql("select id from plans where code = 'vip'")

    for c, started, ends in (
        (companies[0], "now() - interval '1 day'", "now() + interval '1 month'"),
        (companies[1], "now() - interval '1 day'", "now() + interval '1 month'"),
        # Истёкшая подписка — не витрина
        (companies[2], "now() - interval '2 months'", "now() - interval '1 day'"),
    ):
        sql(
            "insert into subscriptions (company_id, plan_id, status, started_at, ends_at, "
            f"created_at, updated_at) values (%s, %s, 'active', {started}, {ends}, now(), now())",
            [c, vip],
        )

    [(type_id,)] = sql("select id from promotion_types where badge is not null order by id limit 1")
    [(promoted,)] = sql(
        "select id from listings where company_id = %s and type = 'supply' order by id limit 1",
        [companies[1]],
    )
    sql(
        "insert into promotions (listing_id, company_id, promotion_type_id, units_spent, status, "
        "starts_at, ends_at, created_at, updated_at) values (%s, %s, %s, 1, 'active', "
        "now() - interval '1 day', now() + interval '1 week', now(), now())",
        [promoted, companies[1], type_id],
    )
    объявление(
        company_id=companies[0],
        price=1234.5,
        currency="USD",
        published_at=Выражение("now() - interval '3 hours'"),
        description="供应优质水泥，" * 40,
    )
    объявление(
        company_id=companies[0],
        price_negotiable=True,
        published_at=Выражение("now() - interval '20 minutes'"),
    )
    объявление(
        company_id=companies[0],
        source="import",
        title_i18n={"en": "Imported cement"},
        published_at=Выражение("now() - interval '5 minutes'"),
    )
    объявление(
        company_id=companies[1],
        type="demand",
        price=99,
        currency="EUR",
        published_at=Выражение("now() - interval '2 days'"),
    )

    # Одинаковая дата у нескольких объявлений: порядок решает номер
    for i in range(1, 7):
        объявление(
            company_id=companies[i % 2],
            published_at=Выражение("date_trunc('minute', now() - interval '2 days')"),
            type="supply" if i % 3 else "demand",
        )

    for i in range(4):
        отзыв(
            company_id=companies[i],
            author_company_id=companies[i + 1],
            created_at=Выражение(f"now() - interval '{i} days'"),
        )


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники()
    фон = КОРЕНЬ / "storage/app/public/appearance/test-hero.png"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(КАДР)
    данные()
    sql(
        "insert into banners (name, placement, url, alt, image_path, focal_x, focal_y, is_active, "
        "is_dismissible, sort, created_at, updated_at) values ('Акция', 'home', '/pricing', "
        "'Скидка', 'banners/a.png', 30, 70, true, true, 0, now(), now())"
    )
    sql(
        "insert into banner_images (banner_id, locale, image_path, image_mobile_path, "
        "created_at, updated_at) select id, 'en', 'banners/en.png', null, now(), now() "
        "from banners"
    )
    sql("update landing_blocks set is_visible = false where key = 'reviews'")
    sql(
        "update settings set value = %s where key = 'hero_image'",
        ['"appearance/test-hero.png"'],
    )
    laravel_cache.put("cbu.rates", КУРСЫ, 86400)

    try:
        with адрес(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        laravel_cache.file_path("cbu.rates").unlink(missing_ok=True)
        фон.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("path", "язык"), [("/", "ru"), ("/uz", "uz"), ("/en", "en"), ("/zh/", "zh"), ("/tr", "tr")]
)
def test_главная(сайт, path, язык):
    д = открыть(сайт, path, env=ФАЙЛОВЫЙ)
    стр = страница(д["body"])
    props = стр["props"]

    assert д["status"] == 200
    assert стр["component"] == "Home"
    assert props["latest"] and props["requests"] and props["suppliers"]
    assert props["heroRatio"] == 1.5
    assert props["heroImage"].endswith("/storage/appearance/test-hero.png")
    # Скрытая секция отзывов — не видна, первый экран виден всегда
    assert props["blocks"]["reviews"]["visible"] is False
    assert props["blocks"]["hero"]["visible"] is True
    assert props["locale"] == язык


def test_витрина_vip_и_цены(сайт):
    д = открыть(сайт, "/en", env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]

    assert props["latest"][0]["promoted"]
    assert any(card["converted"] for card in props["latest"])
    assert props["banner"]["image"].endswith("/storage/banners/en.png")


def test_лента_товаров_без_карточек_витрины_vip(сайт):
    д = открыть(сайт, "/", env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]
    vip = {card["id"] for card in props["latest"]}

    assert props["products"]
    assert not vip & {card["id"] for card in props["products"]}
    assert props["blocks"]["products"]["heading"] == "Товары"


def test_вошедший(сайт):
    uid = пользователь("home@savdex.uz")
    куки = вход(uid)

    д = открыть(сайт, "/", куки, env=ФАЙЛОВЫЙ)
    стр = страница(д["body"])

    assert д["status"] == 200
    assert стр["component"] == "Home"
    assert стр["props"]["auth"]["user"]["email"] == "home@savdex.uz"

    # Без версии сборки — 409: перезагрузка того же адреса — с языковым
    # префиксом (иначе /uz уводило бы на русскую), у корня без «/», а с
    # параметрами — «/?…»
    # «/uz» — последним: заход на него запоминает язык вошедшему
    for path, куда in (("/?utm_source=tg", "/?utm_source=tg"), ("/uz", "/uz")):
        д = открыть(сайт, path, куки, {"X-Inertia": "true"}, env=ФАЙЛОВЫЙ)

        assert д["status"] == 409
        assert д["headers"]["x-inertia-location"] == сайт + куда
