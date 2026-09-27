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

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

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


def test_страница_резюме(сайт):
    # С переводом, фото и местами работы; без контактного имени; с «0»
    for slug, prefix in (
        ("resume-4", ""),
        ("resume-4", "/en"),
        ("resume-8", "/uz"),
        ("resume-9", "/zh"),
        ("resume-3", "/tr"),
    ):
        сверить(сайт, f"{prefix}/resume/{slug}", перед=обнулить)


def обнулить() -> None:
    """Счётчик просмотров — с нуля перед каждой стороной сверки."""
    sql("update resumes set views_count = 0")


def test_переведённые_места_работы(сайт):
    sql(
        "update resumes set jobs_i18n = %s::json where slug = 'resume-12'",
        ['{"en": [{"position": "Supply clerk", "duties": ""}], "uz": [{}, {}]}'],
    )
    for prefix in ("/en", "/uz"):
        сверить(сайт, f"{prefix}/resume/resume-12", перед=обнулить)


def test_нет_резюме(сайт):
    for slug in ("nothing", "resume-48", "resume-49"):
        д, _ = сверить(сайт, f"/resume/{slug}")
        assert д["status"] == 404


def test_контакты_вошедшему_и_просмотры(сайт):
    пользователь("buyer@savdex.uz")
    куки = войти(сайт, "buyer@savdex.uz")
    д, _ = сверить(сайт, "/resume/resume-5", куки, перед=обнулить)
    props = страница(д["body"])["props"]["resume"]

    assert props["contacts"] is not None
    # Своя сторона видит свой просмотр
    assert props["views"] == 1
    assert sql("select views_count from resumes where slug = 'resume-5'")[0][0] == 1

    было = 1
    из_django(сайт, "/resume/resume-5")
    из_laravel(сайт, "/resume/resume-5")
    assert sql("select views_count from resumes where slug = 'resume-5'")[0][0] == было + 2


def test_свой_просмотр_не_считается(сайт):
    email = sql(
        "select u.email from users u join resumes r on r.user_id = u.id where r.slug = 'resume-6'"
    )[0][0]
    sql(
        "update users set password = (select password from users where email = 'buyer@savdex.uz') "
        "where email = %s",
        [email],
    )
    куки = войти(сайт, email)
    было = sql("select views_count from resumes where slug = 'resume-6'")[0][0]

    из_django(сайт, "/resume/resume-6", куки)
    из_laravel(сайт, "/resume/resume-6", куки)

    assert sql("select views_count from resumes where slug = 'resume-6'")[0][0] == было
