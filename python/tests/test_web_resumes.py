"""
Этап 4, шаг 2: «Резюме» на Django неотличимо от Laravel.

Список с поиском (как набрано и в транслитерации, по навыкам — колонка
json), фильтрами сферы, города, опыта и занятости и постраничным
выводом — копией LengthAwarePaginator: окно номеров с «...», адреса
страниц с параметрами запроса, странные номера страниц.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

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
    # 47 опубликованных (3 страницы по 20), черновик, удалённое;
    # у части — перевод должности, фото, пустое имя «0», удалённый автор
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$cities = App\\Models\\City::where('country_id', $uz)->orderBy('id')"
        "->limit(3)->pluck('id');"
        "$fields = ['sales', 'procurement', 'logistics', 'it'];"
        "$titles = ['Менеджер по снабжению', 'Водитель-экспедитор', 'Sotuv menejeri', "
        "'Инженер-сметчик', 'Бухгалтер'];"
        "foreach (range(1, 49) as $i) {"
        " $u = App\\Models\\User::factory()->create("
        "['name' => $i % 7 ? 'Азиз Каримов '.$i : 'Madina']);"
        " $r = new App\\Models\\Resume();"
        " $r->forceFill(['user_id' => $u->id, 'slug' => 'resume-'.$i,"
        "  'title' => $titles[$i % 5], 'field' => $fields[$i % 4],"
        "  'country_id' => $i % 3 ? $uz : null, 'city_id' => $i % 3 ? $cities[$i % 3] : null,"
        "  'salary' => $i % 4 ? 1000000 * $i : null, 'currency' => $i % 2 ? 'UZS' : 'USD',"
        "  'employment' => $i % 2 ? ['full'] : ['part', 'project'],"
        "  'experience_months' => ($i * 5) % 100,"
        "  'about' => $i % 6 ? 'Опыт в закупках цемента и арматуры.' : null,"
        "  'skills' => $i % 5 ? ['1C', 'Excel', 'AutoCAD '.$i, 'Переговоры', "
        "'a', 'b', 'c', 'd', 'e'] : null,"
        "  'jobs' => [['company' => 'Stroy Group', 'position' => 'Snabjenec']],"
        "  'title_i18n' => $i % 4 === 0 ? ['en' => 'Supply manager', 'uz' => ''] : null,"
        "  'photo_path' => $i % 9 === 0 ? 'resumes/p'.$i.'.jpg' : null,"
        "  'contact_name' => $i % 8 === 0 ? '0' : ($i % 3 ? null : 'Сардор  Алиев'),"
        "  'status' => $i === 48 ? 'draft' : 'published',"
        "  'published_at' => Carbon\\Carbon::parse('2026-09-01 12:00:00')->subHours($i % 10),"
        " ])->save();"
        " if ($i === 49) { $r->delete(); }"
        " if ($i === 10) { $u->delete(); }"
        "}"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/resumes",
        "/resumes?page=2",
        "/resumes?page=3&field=it",
        "/resumes?page=9",
        "/resumes?page=abc",
        "/resumes?page=02",
        "/resumes?page=%202%20",
        "/resumes?page=-1",
        "/en/resumes?page=2",
        "/uz/resumes",
        "/zh/resumes?q=supply",
        "/tr/resumes?employment=full",
    ],
)
def test_список_и_страницы(сайт, path):
    сверить(сайт, path)


@pytest.mark.parametrize(
    "path",
    [
        "/resumes?q=%D1%81%D0%BD%D0%B0%D0%B1%D0%B6%D0%B5%D0%BD",
        "/resumes?q=snabjen",
        "/resumes?q=%20%20Excel%20",
        "/resumes?q=autocad%2012",
        "/resumes?q=g%CA%BBisht",
        "/resumes?q=",
        "/resumes?q=%27",
        "/resumes?field=logistics&city=abc",
        "/resumes?field=nonsense",
        "/resumes?experience=from3&employment=project",
        "/resumes?experience=from6",
        "/resumes?employment=0",
        "/resumes?z=1&page=2&field=sales&a=%7E",
    ],
)
def test_поиск_и_фильтры(сайт, path):
    сверить(сайт, path)


def test_фильтр_по_городу(сайт):
    д, _ = сверить(сайт, "/resumes")
    города = страница(д["body"])["props"]["cities"]

    assert города
    сверить(сайт, f"/resumes?city={города[0]['id']}&page=1")


def test_подписи_назад_вперёд(сайт):
    """Своего файла pagination у площадки нет: перевод — только английский."""
    подписи = (("/resumes", "pagination.previous"), ("/en/resumes", "&laquo; Previous"))

    for path, previous in подписи:
        д, _ = сверить(сайт, path)

        assert страница(д["body"])["props"]["resumes"]["links"][0]["label"] == previous


@pytest.mark.parametrize(
    ("path", "найдено"),
    [
        # должность кириллицей, запрос латиницей — и наоборот
        ("/resumes?q=snabjen", 47),
        ("/resumes?q=%D1%81%D0%BD%D0%B0%D0%B1%D0%B6%D0%B5%D0%BD", 47),
        # навыки — json: на PostgreSQL у Laravel здесь была ошибка 500
        ("/resumes?q=autocad%2012", 1),
        ("/resumes?field=it&employment=full", 12),
        ("/resumes?field=it&employment=project", 0),
    ],
)
def test_поиск_находит(сайт, path, найдено):
    д, _ = сверить(сайт, path)

    assert страница(д["body"])["props"]["total"] == найдено
