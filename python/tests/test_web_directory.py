"""
«Страны» и «Партнёры» на Django неотличимы от Laravel (этап 3).

Страны: работающие и запланированные, порядок по полю sort и названию
по правилам языка (ICU), витрина до 12 компаний на страну. Партнёры:
генеральные и обычные, тип компании из справочника или правовая форма,
город и страна на языке посетителя, счётчики.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    for seeder in ("GeoSeeder",):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            capture_output=True,
            check=True,
        )

    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$kz = App\\Models\\Country::where('code', 'kz')->value('id');"
        "$city = App\\Models\\City::where('country_id', $uz)->value('id');"
        "$make = fn (array $a) => App\\Models\\Company::factory()->create($a);"
        "foreach (range(1, 14) as $i) { $make(['country_id' => $uz, 'city_id' => $city, "
        "'rating' => $i % 5, 'verification_level' => $i % 3]); }"
        "$make(['country_id' => $kz, 'city_id' => null, 'type' => null, "
        "'legal_form' => 'freelancer', 'partner_tier' => 'general', 'partner_sort' => 2]);"
        "$make(['country_id' => $kz, 'city_id' => null, 'type' => null, "
        "'legal_form' => 'legal', 'partner_tier' => 'general', 'partner_sort' => 1]);"
        "$make(['country_id' => $uz, 'city_id' => $city, 'partner_tier' => 'partner', "
        "'rating' => 4.5]);"
        "$make(['country_id' => $uz, 'city_id' => null, 'status' => 'blocked', "
        "'partner_tier' => 'partner']);"
        "App\\Models\\Listing::factory()->count(3)->create();"
        "echo 'ok';"
    )
    # Одинаковый sort у трёх стран — порядок решает название по правилам языка
    sql("update countries set sort = 5 where code in ('tr', 'cn', 'ru')")

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path", ["/countries", "/uz/countries", "/en/countries", "/zh/countries", "/tr/countries"]
)
def test_страны(сайт, path):
    д, _ = сверить(сайт, path)
    props = страница(д["body"])["props"]

    assert props["countries"] and props["planned"]
    assert all(len(c["items"]) <= 12 for c in props["countries"])


@pytest.mark.parametrize("path", ["/partners", "/en/partners", "/zh/partners"])
def test_партнёры(сайт, path):
    д, _ = сверить(сайт, path)
    props = страница(д["body"])["props"]

    assert len(props["general"]) == 2 and len(props["partners"]) == 1
