"""
Этап 4, шаг 1: общий с Laravel счётчик частоты, «Показать ещё» на
странице стран и старый адрес /tenders.

Счётчик throttle у Laravel — в файловом кэше, ключ — посетитель, а не
адрес. Запросы попеременно к Laravel и к Django идут в один счётчик:
60-й проходит, 61-й — 429 с обеих сторон, страницы ошибки одинаковые.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить

pytestmark = нужна_база

ФАЙЛОВЫЙ = {"CACHE_STORE": "file"}


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
        ["php", "artisan", "db:seed", "--class=GeoSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$city = App\\Models\\City::where('country_id', $uz)->value('id');"
        "foreach (range(1, 9) as $i) { $c = App\\Models\\Company::factory()->create(["
        "'country_id' => $uz, 'city_id' => $i % 2 ? $city : null, 'rating' => $i % 4, "
        "'verification_level' => $i % 3, 'type' => $i === 3 ? null : 'importer', "
        "'legal_form' => $i === 3 ? 'freelancer' : 'legal']);"
        " App\\Models\\Listing::factory()->count($i % 3)->create(['company_id' => $c->id]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    очистить_кэш()

    try:
        with laravel(**ФАЙЛОВЫЙ) as root:
            yield root
    finally:
        очистить_кэш()


def json_сверка(сайт: str, path: str, headers: dict[str, str]) -> dict:
    д = из_django(сайт, path, headers=headers, env=ФАЙЛОВЫЙ)
    л = из_laravel(сайт, path, headers=headers)

    assert д["status"] == л["status"] == 200, (д["status"], л["status"])
    assert json.loads(д["body"]) == json.loads(л["body"])
    assert д["headers"]["content-type"].startswith("application/json")

    return dict(json.loads(д["body"]))


@pytest.mark.parametrize(
    ("path", "ip"),
    [
        ("/countries/uz/companies", "198.51.100.1"),
        ("/countries/UZ/companies?offset=3", "198.51.100.2"),
        ("/en/countries/uz/companies?offset=2abc", "198.51.100.3"),
        ("/zh/countries/uz/companies?offset=-5", "198.51.100.4"),
        ("/tr/countries/uz/companies?offset=100", "198.51.100.5"),
    ],
)
def test_показать_ещё(сайт, path, ip):
    данные = json_сверка(сайт, path, {"X-Forwarded-For": ip})

    assert isinstance(данные["items"], list)


def test_нет_такой_страны(сайт):
    ip = {"X-Forwarded-For": "198.51.100.9"}
    сверить(сайт, "/countries/xx/companies", headers=ip, env=ФАЙЛОВЫЙ)


@pytest.mark.parametrize(
    "path",
    [
        "/tenders",
        "/tenders?q=%20цемент%20м400%20&category=12abc&closed=yes",
        "/tenders?q=a~b&closed=0&category=0",
        "/uz/tenders?closed=on",
    ],
)
def test_старый_адрес_закупок(сайт, path):
    д, _ = сверить(сайт, path, env=ФАЙЛОВЫЙ)

    assert д["status"] == 301


def test_общий_счётчик_частоты(сайт):
    """60 запросов в минуту на посетителя — сколько бы ни было у Laravel и у Django."""
    ip = {"X-Forwarded-For": "203.0.113.77"}
    path = "/countries/uz/companies"

    for _ in range(58):
        assert из_laravel(сайт, path, headers=ip)["status"] == 200

    д = из_django(сайт, path, headers=ip, env=ФАЙЛОВЫЙ)
    assert (д["status"], д["headers"]["x-ratelimit-remaining"]) == (200, "1")

    л = из_laravel(сайт, path, headers=ip)
    assert (л["status"], л["headers"]["x-ratelimit-remaining"]) == (200, "0")

    # 61-й — отказ с обеих сторон, и страница отказа одинаковая
    д, л = сверить(сайт, path, headers=ip, env=ФАЙЛОВЫЙ)
    assert д["status"] == л["status"] == 429

    # Другой посетитель считается отдельно
    д = из_django(сайт, path, headers={"X-Forwarded-For": "203.0.113.78"}, env=ФАЙЛОВЫЙ)
    assert (д["status"], д["headers"]["x-ratelimit-remaining"]) == (200, "59")


def test_вошедший_считается_по_учётной_записи(сайт):
    пользователь("throttle@savdex.uz")
    куки = войти(сайт, "throttle@savdex.uz")
    path = "/countries/uz/companies"

    л = из_laravel(сайт, path, куки, {"X-Forwarded-For": "203.0.113.90"})
    # Другой адрес, та же учётная запись — тот же счётчик
    д = из_django(сайт, path, куки, {"X-Forwarded-For": "203.0.113.91"}, env=ФАЙЛОВЫЙ)

    осталось = int(л["headers"]["x-ratelimit-remaining"])
    assert int(д["headers"]["x-ratelimit-remaining"]) == осталось - 1
