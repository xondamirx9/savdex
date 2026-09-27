"""
Этап 4, шаг 3: каталог компаний /companies на Django неотличим от Laravel.

Поиск (обе графики и ИНН), фильтры типа, страны, проверки и возраста,
счётчики вариантов каждого фильтра при остальных, постраничный вывод
по 12, карточка (заполненность профиля, «на площадке с», сайт).
Ограничение частоты — общее с Laravel (120 в минуту).

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, нужна_база, свежая_база
from .web_site import laravel, из_django, из_laravel, сверить, страница

pytestmark = нужна_база


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
    # 30 активных (три страницы по 12) в двух странах, разных типов,
    # возрастов и проверки; заблокированная и удалённая — не в каталоге
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$kz = App\\Models\\Country::where('code', 'kz')->value('id');"
        "$city = App\\Models\\City::where('country_id', $uz)->value('id');"
        "$types = ['importer', 'manufacturer', 'distributor', null];"
        "foreach (range(1, 30) as $i) { $c = App\\Models\\Company::factory()->create(["
        "'name' => $i % 5 ? 'ООО Цемент '.$i : 'Sement Savdo '.$i,"
        "'tin' => (string) (300000000 + $i), 'country_id' => $i % 4 ? $uz : $kz,"
        "'city_id' => $i % 3 ? $city : null, 'type' => $types[$i % 4],"
        "'legal_form' => $i % 7 ? 'legal' : 'individual',"
        "'verification_level' => $i % 3, 'rating' => ($i % 5) + 0.5,"
        "'website' => $i % 6 ? null : ($i % 4 ? 'savdo'.$i.'.uz' : 'https://x'.$i.'.uz'),"
        "'description' => $i % 2 ? str_repeat('Поставки цемента. ', 8) : null]);"
        " $c->forceFill(['created_at' => now()->subMonths($i * 3)])->save();"
        " if ($i % 8 === 0) { $c->documents()->forceCreate(['type' => 'registration',"
        " 'title' => 'Свидетельство', 'file_path' => 'docs/'.$i.'.pdf',"
        " 'moderation_status' => 'approved']); } }"
        "App\\Models\\Company::factory()->create(['status' => 'blocked']);"
        "App\\Models\\Company::factory()->create()->delete();"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/companies",
        "/companies?page=2",
        "/companies?page=3",
        "/companies?page=4",
        "/en/companies?page=2",
        "/uz/companies",
        "/zh/companies?type=importer",
        "/tr/companies?country=KZ",
        "/companies?q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82",
        "/companies?q=sement",
        "/companies?q=%20300000012%20",
        "/companies?q=0",
        "/companies?q=",
        "/companies?verified=1",
        "/companies?verified=1&type=manufacturer&country=uz",
        "/companies?age=lt1",
        "/companies?age=1to5&page=2",
        "/companies?age=gt5",
        "/companies?age=old",
        "/companies?type=nonsense",
        "/companies?country=hu",
        "/companies?z=1&age=&verified=0",
    ],
)
def test_каталог(сайт, path):
    сверить(сайт, path)


def test_фильтры_считают_варианты(сайт):
    д, _ = сверить(сайт, "/companies?country=uz")
    props = страница(д["body"])["props"]

    # Страна выбрана, а счётчик стран — без неё: видно, что даст другая
    assert {c["code"] for c in props["countries"]} == {"uz", "kz"}
    assert props["filters"] == {"country": "uz"}
    assert sum(props["facets"]["ages"].values()) == props["companies"]["total"]


def test_без_фильтров_пустой_список(сайт):
    д, _ = сверить(сайт, "/companies")

    assert страница(д["body"])["props"]["filters"] == []


def test_ограничение_частоты(сайт):
    """Лимит 120 — свой у маршрута, счётчик — общий с Laravel."""
    файловый = {"CACHE_STORE": "file"}
    ip = {"X-Forwarded-For": "203.0.113.120"}

    with laravel(**файловый) as root:
        л = из_laravel(root, "/companies", headers=ip)
        д = из_django(root, "/companies", headers=ip, env=файловый)

    assert л["headers"]["x-ratelimit-limit"] == д["headers"]["x-ratelimit-limit"] == "120"
    assert (
        int(д["headers"]["x-ratelimit-remaining"]) == int(л["headers"]["x-ratelimit-remaining"]) - 1
    )
