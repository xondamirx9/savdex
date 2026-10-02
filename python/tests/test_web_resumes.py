"""
Этап 4, шаг 2: «Резюме» на Django.

Список с поиском (как набрано и в транслитерации, по навыкам — колонка
json), фильтрами сферы, города, опыта и занятости и постраничным
выводом — копией LengthAwarePaginator: окно номеров с «...», адреса
страниц с параметрами запроса, странные номера страниц.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator

import pytest

from . import factories
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

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


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    справочники("countries", "country_translations", "cities", "city_translations")

    # 47 опубликованных, черновик, удалённое; у части — перевод должности,
    # фото, пустое имя «0»; у одного автор удалён — его резюме не видно (46)
    [(uz,)] = sql("select id from countries where code = 'uz'")
    cities = [
        c for (c,) in sql("select id from cities where country_id = %s order by id limit 3", [uz])
    ]
    fields = ["sales", "procurement", "logistics", "it"]
    titles = ["Менеджер по снабжению", "Водитель-экспедитор", "Sotuv menejeri",
              "Инженер-сметчик", "Бухгалтер"]  # fmt: skip

    for i in range(1, 50):
        uid = factories.пользователь(name=f"Азиз Каримов {i}" if i % 7 else "Madina")
        поля = {
            "user_id": uid,
            "slug": f"resume-{i}",
            "title": titles[i % 5],
            "field": fields[i % 4],
            "country_id": uz if i % 3 else None,
            "city_id": cities[i % 3] if i % 3 else None,
            "salary": 1_000_000 * i if i % 4 else None,
            "currency": "UZS" if i % 2 else "USD",
            "employment": json.dumps(["full"] if i % 2 else ["part", "project"]),
            "experience_months": (i * 5) % 100,
            "about": "Опыт в закупках цемента и арматуры." if i % 6 else None,
            "skills": json.dumps(
                ["1C", "Excel", f"AutoCAD {i}", "Переговоры", "a", "b", "c", "d", "e"]
            )
            if i % 5
            else None,
            "jobs": json.dumps([{"company": "Stroy Group", "position": "Snabjenec"}]),
            "title_i18n": json.dumps({"en": "Supply manager", "uz": ""}) if i % 4 == 0 else None,
            "photo_path": f"resumes/p{i}.jpg" if i % 9 == 0 else None,
            "contact_name": "0" if i % 8 == 0 else (None if i % 3 else "Сардор  Алиев"),
            "status": "draft" if i == 48 else "published",
            "published_at": f"2026-09-01 {12 - i % 10:02d}:00:00",
        }
        sql(
            f"insert into resumes ({', '.join(поля)}, created_at, updated_at) "
            f"values ({', '.join(['%s'] * len(поля))}, now(), now())",
            list(поля.values()),
        )

        if i == 49:
            sql("update resumes set deleted_at = now() where slug = 'resume-49'")

        if i == 10:
            sql("update users set deleted_at = now() where id = %s", [uid])

    with адрес() as root:
        yield root


def список(сайт: str, path: str) -> dict:
    """Пропсы списка резюме; номер активной ссылки — текущая страница."""
    д = открыть(сайт, path)
    стр = страница(д["body"])

    assert д["status"] == 200 and стр["component"] == "resumes/Index"

    return dict(стр["props"])


@pytest.mark.parametrize(
    ("path", "всего", "страница_", "последняя", "на_странице"),
    [
        # 49 резюме: без черновика, удалённого и резюме удалённого автора —
        # 46, по 20 на страницу
        ("/resumes", 46, 1, 3, 20),
        ("/resumes?page=2", 46, 2, 3, 20),
        # За последней страницей — пусто, но номер страницы тот, что просили
        ("/resumes?page=3&field=it", 12, 3, 1, 0),
        ("/resumes?page=9", 46, 9, 3, 0),
        # Не номер, ведущий ноль, меньше единицы — первая; пробелы вокруг — можно
        ("/resumes?page=abc", 46, 1, 3, 20),
        ("/resumes?page=02", 46, 1, 3, 20),
        ("/resumes?page=%202%20", 46, 2, 3, 20),
        ("/resumes?page=-1", 46, 1, 3, 20),
        ("/en/resumes?page=2", 46, 2, 3, 20),
        ("/uz/resumes", 46, 1, 3, 20),
        ("/zh/resumes?q=supply", 0, 1, 1, 0),
        ("/tr/resumes?employment=full", 24, 1, 2, 20),
    ],
)
def test_список_и_страницы(сайт, path, всего, страница_, последняя, на_странице):
    props = список(сайт, path)
    resumes = props["resumes"]

    assert props["total"] == resumes["total"] == всего
    assert (resumes["current_page"], resumes["last_page"]) == (страница_, последняя)
    assert len(resumes["data"]) == на_странице
    # Ссылки: «назад», номера страниц окна, «вперёд»
    номера = [link["label"] for link in resumes["links"][1:-1]]
    assert номера == [str(n) for n in range(1, последняя + 1)]
    активные = [link["label"] for link in resumes["links"] if link["active"]]
    assert активные == ([str(страница_)] if страница_ <= последняя else [])


@pytest.mark.parametrize(
    ("path", "всего", "фильтры", "первая"),
    [
        # Должность и места работы — как набрано и в транслитерации
        ("/resumes?q=%D1%81%D0%BD%D0%B0%D0%B1%D0%B6%D0%B5%D0%BD", 46, {"q": "снабжен"}, None),
        ("/resumes?q=snabjen", 46, {"q": "snabjen"}, None),
        # Пробелы вокруг запроса отбрасываются; навыки — колонка json
        ("/resumes?q=%20%20Excel%20", 38, {"q": "Excel"}, "/resumes?q=Excel&page=1"),
        ("/resumes?q=autocad%2012", 1, {"q": "autocad 12"}, None),
        ("/resumes?q=g%CA%BBisht", 0, {"q": "gʻisht"}, None),
        ("/resumes?q=", 46, {"q": ""}, "/resumes?page=1"),
        ("/resumes?q=%27", 46, {"q": "'"}, None),
        # Город не числом — без фильтра по городу
        ("/resumes?field=logistics&city=abc", 11, {"field": "logistics", "city": None}, None),
        # Неизвестная сфера — без фильтра, но в форме остаётся
        ("/resumes?field=nonsense", 46, {"field": "nonsense"}, None),
        (
            "/resumes?experience=from3&employment=project",
            11,
            {"experience": "from3", "employment": "project"},
            None,
        ),
        ("/resumes?experience=from6", 10, {"experience": "from6"}, None),
        ("/resumes?employment=0", 46, {"employment": None}, "/resumes?employment=0&page=1"),
        # Чужие параметры запроса остаются в адресах страниц
        (
            "/resumes?z=1&page=2&field=sales&a=%7E",
            11,
            {"field": "sales"},
            "/resumes?z=1&field=sales&a=~&page=1",
        ),
    ],
)
def test_поиск_и_фильтры(сайт, path, всего, фильтры, первая):
    props = список(сайт, path)

    assert props["total"] == props["resumes"]["total"] == всего
    assert {k: props["filters"][k] for k in фильтры} == фильтры

    if первая is not None:
        assert props["resumes"]["first_page_url"] == сайт + первая


def test_фильтр_по_городу(сайт):
    города = список(сайт, "/resumes")["cities"]

    # Города, где есть резюме, — по названию
    assert [г["name"] for г in города] == ["Бухара", "Самарканд"]

    props = список(сайт, f"/resumes?city={города[0]['id']}&page=1")
    assert props["filters"]["city"] == города[0]["id"]
    assert props["total"] == 16
    assert {r["city"] for r in props["resumes"]["data"]} == {"Бухара"}


def test_подписи_назад_вперёд(сайт):
    """По-английски — подпись фреймворка, на русском — из словаря интерфейса."""
    подписи = (("/resumes", "&laquo; Назад"), ("/en/resumes", "&laquo; Previous"))

    for path, previous in подписи:
        assert список(сайт, path)["resumes"]["links"][0]["label"] == previous


@pytest.mark.parametrize(
    ("path", "найдено"),
    [
        # должность кириллицей, запрос латиницей — и наоборот
        ("/resumes?q=snabjen", 46),
        ("/resumes?q=%D1%81%D0%BD%D0%B0%D0%B1%D0%B6%D0%B5%D0%BD", 46),
        # навыки — json: на PostgreSQL у Laravel здесь была ошибка 500
        ("/resumes?q=autocad%2012", 1),
        ("/resumes?field=it&employment=full", 12),
        ("/resumes?field=it&employment=project", 0),
    ],
)
def test_поиск_находит(сайт, path, найдено):
    assert список(сайт, path)["total"] == найдено


def обнулить() -> None:
    """Счётчик просмотров — с нуля перед каждым заходом."""
    sql("update resumes set views_count = 0")


def резюме(сайт: str, path: str, cookies: dict[str, str] | None = None) -> dict:
    д = открыть(сайт, path, cookies)
    стр = страница(д["body"])

    assert д["status"] == 200 and стр["component"] == "resumes/Show"

    return dict(стр["props"]["resume"])


@pytest.mark.parametrize(
    ("slug", "prefix", "ожидание"),
    [
        ("resume-4", "", {"title": "Бухгалтер", "name": "Азиз Каримов 4", "city": "Самарканд"}),
        # Перевод должности
        ("resume-4", "/en", {"title": "Supply manager", "city": "Samarkand"}),
        # Пустой перевод — русская должность; имя «0» — имя пользователя
        (
            "resume-8",
            "/uz",
            {"title": "Инженер-сметчик", "name": "Азиз Каримов 8", "city": "Buxoro"},
        ),
        # Контактное имя как есть, фото с диска, без города
        ("resume-9", "/zh", {"name": "Сардор  Алиев", "city": None, "country": None}),
        (
            "resume-3",
            "/tr",
            {
                "title": "Инженер-сметчик",
                "experience": {"years": 1, "months": 3},
                "salary": 3000000,
            },
        ),
    ],
)
def test_страница_резюме(сайт, slug, prefix, ожидание):
    обнулить()
    resume = резюме(сайт, f"{prefix}/resume/{slug}")

    assert resume["slug"] == slug
    assert {k: resume[k] for k in ожидание} == ожидание
    # Гость контактов не видит; навыков — не больше восьми; просмотр засчитан
    assert resume["contacts"] is None
    assert len(resume["skills"]) <= 8
    assert resume["views"] == 1
    assert resume["jobs"] == [{"company": "Stroy Group", "position": "Snabjenec"}]

    if slug == "resume-9":
        assert resume["photo"] == f"{сайт}/storage/resumes/p9.jpg"


def test_переведённые_места_работы(сайт):
    sql(
        "update resumes set jobs_i18n = %s::json where slug = 'resume-12'",
        ['{"en": [{"position": "Supply clerk", "duties": ""}], "uz": [{}, {}]}'],
    )
    обнулить()

    # Перевод поверх места работы: компания своя, должность переведена
    assert резюме(сайт, "/en/resume/resume-12")["jobs"] == [
        {"company": "Stroy Group", "position": "Supply clerk", "duties": ""}
    ]
    # Перевод пустой и не той длины — места работы как написаны
    assert резюме(сайт, "/uz/resume/resume-12")["jobs"] == [
        {"company": "Stroy Group", "position": "Snabjenec"}
    ]


def test_нет_резюме(сайт):
    for slug in ("nothing", "resume-48", "resume-49"):
        д = открыть(сайт, f"/resume/{slug}")
        assert д["status"] == 404
        assert страница(д["body"])["component"] == "Error"


def test_контакты_вошедшему_и_просмотры(сайт):
    куки = вход(пользователь("buyer@savdex.uz"))
    обнулить()
    props = резюме(сайт, "/resume/resume-5", куки)

    assert props["contacts"] is not None
    # Свой просмотр виден сразу
    assert props["views"] == 1
    assert sql("select views_count from resumes where slug = 'resume-5'")[0][0] == 1

    открыть(сайт, "/resume/resume-5")
    assert sql("select views_count from resumes where slug = 'resume-5'")[0][0] == 2


def test_свой_просмотр_не_считается(сайт):
    [(uid,)] = sql("select user_id from resumes where slug = 'resume-6'")
    было = sql("select views_count from resumes where slug = 'resume-6'")[0][0]

    резюме(сайт, "/resume/resume-6", вход(uid))

    assert sql("select views_count from resumes where slug = 'resume-6'")[0][0] == было
