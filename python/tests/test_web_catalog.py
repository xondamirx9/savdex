"""
Этап 4, шаг 7: каталог объявлений /catalog на Django неотличим от Laravel.

Выдача: живые объявления активных компаний, на других языках — без
импортированных непереведённых; поиск, тип, раздел с подразделами,
город, проверенные, с ценой; сортировки (подходящие — продвинутые
выше), постраничный вывод. И статистика: показы (listings, listing_stats)
с отсевом повторов и поисковые запросы (search_hits) — у Django ровно
то же, что у Laravel.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, из_django, из_laravel, сверить, страница

pytestmark = нужна_база

#: Файловый кэш, общий с Laravel: курс ЦБ для цен в валюте языка Django
#: берёт из него (в CI у Laravel есть сеть, и курс он получает сам)
ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}

#: Ключи курса ЦБ в кэше Laravel (CurrencyRate)
КУРС = ("cbu.rates", "cbu.rates.last", "cbu.rate.usd.last")


def очистить_кэш() -> None:
    """Кэш с нуля — заодно и счётчик ограничения частоты."""
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

    for seeder in ("GeoSeeder", "CategorySeeder", "PromotionTypeSeeder"):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    # 26 живых (две страницы) у трёх компаний, импорт без перевода,
    # черновик, объявление заблокированной компании; продвижения
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$cities = App\\Models\\City::where('country_id', $uz)->orderBy('id')"
        "->limit(2)->pluck('id');"
        "$root = App\\Models\\Category::whereNull('parent_id')->orderBy('sort')->first();"
        "$child = App\\Models\\Category::where('parent_id', $root->id)->orderBy('sort')->first();"
        "$other = App\\Models\\Category::whereNull('parent_id')->orderBy('sort')"
        "->skip(1)->first();"
        "$companies = collect(range(0, 2))->map(fn ($i) => App\\Models\\Company::factory()"
        "->create(['verification_level' => $i, 'city_id' => $cities[$i % 2]]));"
        "$ids = [];"
        "foreach (range(1, 26) as $i) { $l = App\\Models\\Listing::factory()->create(["
        "'company_id' => $companies[$i % 3]->id, 'type' => $i % 4 ? 'supply' : 'demand',"
        "'title' => ($i % 5 ? 'Цемент М400 ' : 'Sement M500 ').$i,"
        "'category_id' => [$root->id, $child->id, $other->id][$i % 3],"
        "'city_id' => $cities[$i % 2], 'price' => $i % 6 ? 100000 * ($i % 7) : null,"
        "'price_negotiable' => $i % 9 === 0,"
        "'published_at' => Carbon\\Carbon::parse('2026-09-20 12:00:00')->subHours($i % 8)]);"
        " $ids[] = $l->id; }"
        "App\\Models\\Listing::factory()->create(['source' => 'import', 'title_i18n' => null,"
        "'company_id' => $companies[0]->id]);"
        "App\\Models\\Listing::factory()->draft()->create(['company_id' => $companies[0]->id]);"
        "$blocked = App\\Models\\Company::factory()->create(['status' => 'blocked']);"
        "App\\Models\\Listing::factory()->create(['company_id' => $blocked->id]);"
        "$types = App\\Models\\PromotionType::pluck('id', 'code');"
        "foreach ([[$ids[20], 'bump'], [$ids[21], 'highlight'], [$ids[22], 'urgent']]"
        " as [$id, $code]) { App\\Models\\Promotion::create(['listing_id' => $id,"
        " 'company_id' => App\\Models\\Listing::find($id)->company_id,"
        " 'promotion_type_id' => $types[$code], 'units_spent' => 1, 'status' => 'active',"
        " 'starts_at' => now(), 'ends_at' => now()->addDays(7)]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    очистить_кэш()
    # Курс ЦБ — в кэш заранее: Laravel не пойдёт за ним в сеть (в CI она
    # есть, локально нет), и цены в валюте языка у обеих сторон одни
    php(
        "Illuminate\\Support\\Facades\\Cache::put('cbu.rates', ['USD' => 12650.5,"
        "'CNY' => 1760.25, 'TRY' => 305.1, 'EUR' => 13710.0, 'RUB' => 140.2, 'KZT' => 25.3],"
        "now()->addDay());"
        "echo 'ok';",
        ФАЙЛОВЫЙ,
    )

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()


def без_кэша() -> None:
    """
    Файлы кэша Laravel — прочь (отсев повторов и счётчик частоты с нуля),
    кроме курса ЦБ: его Django берёт из этого кэша, а в CI Laravel
    получает курс из сети.
    """
    import hashlib

    курс = {hashlib.sha1(k.encode()).hexdigest() for k in КУРС}

    for файл in (КОРЕНЬ / "storage/framework/cache/data").rglob("*"):
        if файл.is_file() and файл.name not in курс:
            файл.unlink(missing_ok=True)


def обнулить() -> None:
    """Статистика с нуля перед каждой стороной сверки."""
    без_кэша()
    sql("update listings set impressions_count = 0")
    sql("delete from listing_stats")
    sql("delete from search_hits")


@pytest.mark.parametrize(
    "path",
    [
        "/catalog",
        "/catalog?page=2",
        "/en/catalog",
        "/uz/catalog?page=2",
        "/catalog?sort=fresh",
        "/catalog?sort=cheap&page=2",
        "/catalog?sort=expensive",
        "/catalog?sort=nonsense",
        "/catalog?type=demand",
        "/catalog?type=supply&verified=1",
        "/catalog?with_price=yes",
        "/catalog?city=abc",
        "/catalog?q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82",
        "/catalog?q=sement",
        "/catalog?q=%20%20",
        "/zh/catalog?q=0&type=0",
        "/tr/catalog?q=%D0%BD%D0%B5%D1%82%D1%83",
    ],
)
def test_выдача(сайт, path):
    сверить(сайт, path, перед=обнулить, env=ФАЙЛОВЫЙ)


def test_раздел_и_город(сайт):
    д, _ = сверить(сайт, "/catalog", перед=обнулить, env=ФАЙЛОВЫЙ)
    props = страница(д["body"])["props"]
    раздел = props["categories"][0]["id"]
    город = props["cities"][0]["id"]

    сверить(сайт, f"/catalog?category={раздел}&city={город}", перед=обнулить, env=ФАЙЛОВЫЙ)


def статистика() -> tuple[object, ...]:
    return (
        sql("select id, impressions_count from listings order by id"),
        sql("select listing_id, date, impressions, views from listing_stats order by listing_id"),
        sql("select company_id, query, date, impressions from search_hits order by company_id"),
    )


@pytest.mark.parametrize(
    # «М400» — кириллицей, как в заголовках
    "path",
    ["/catalog?page=2", "/catalog?q=%20%D0%A6%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%20%20%D0%9C400"],
)
def test_статистика_как_у_laravel(сайт, path):
    обнулить()
    из_laravel(сайт, path)
    laravel_side = статистика()

    обнулить()
    из_django(сайт, path, env=ФАЙЛОВЫЙ)

    assert статистика() == laravel_side
    assert laravel_side[0] and any(n for _, n in laravel_side[0])


def test_повтор_показа_отсеивает_общий_кэш(сайт):
    """Одна сессия: Laravel засчитал показы — Django в течение получаса их не считает."""
    import httpx

    # Сессия — в базе, чтобы Django её узнал; кэш — файловый, общий
    файловый = {"CACHE_STORE": "file", "SESSION_DRIVER": "database"}

    with laravel(**файловый) as root:
        обнулить()
        ответ = httpx.get(root + "/catalog", timeout=30)
        куки = {k: v for k, v in ответ.cookies.items() if k.endswith("-session")}
        assert куки
        assert sql("select sum(impressions_count) from listings")[0][0] > 0

        sql("update listings set impressions_count = 0")
        из_django(root, "/catalog", куки, env=файловый)
        assert sql("select sum(impressions_count) from listings")[0][0] == 0

        # Другая страница — другие объявления, их Django засчитывает
        из_django(root, "/catalog?page=2", куки, env=файловый)
        assert sql("select sum(impressions_count) from listings")[0][0] > 0
