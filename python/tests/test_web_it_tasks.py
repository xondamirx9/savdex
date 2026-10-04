"""
Этап 4, шаг 2: лента «IT-услуги» на Django.

Открытые и выполненные задачи, поиск по search_text, направления и
виды, город, «проверенные», «с бюджетом», постраничный вывод; карточка
с исполнителем и адресом результата; для вошедшего — исполнитель ли он.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from .factories import it_задача, компания
from .factories import пользователь as учётка_фабрики
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес as адрес_сайта
from .web_site import вход, открыть, пользователь, страница

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
    # 26 открытых (две страницы), 3 выполненных, закрытая и задача
    # заблокированной компании
    [(uz,)] = sql("select id from countries where code = 'uz'")
    cities = [c for (c,) in sql("select id from cities where country_id = %s order by id", [uz])]
    types = ["web", "mobile", "logistics", "hr", "accounting", "design"]
    budgets = ["fixed", "range", "negotiable"]
    companies = [
        компания(
            name=f"Заказчик {i}",
            country_id=uz,
            city_id=cities[i % 2] if i < 3 else None,
            verification_level=i,
            is_it_provider=i == 1,
        )
        for i in range(4)
    ]
    начало = datetime(2026, 9, 1, 12, 0, 0)

    for i in range(1, 27):
        it_задача(
            company_id=companies[i % 4],
            service_type=types[i % 6],
            budget_type=budgets[i % 3],
            budget_to=50000000 if i % 3 == 1 else None,
            budget_from=None if i % 3 == 2 else 1500000.5,
            # «2026-10-32» у Carbon — 1 ноября: дни сверх месяца переносятся
            deadline_at=date(2026, 10, 10) + timedelta(days=i) if i % 5 else None,
            title=f"Сайт для склада {i}" if i % 7 else f"Sayt yaratish {i}",
            published_at=начало - timedelta(hours=i % 9),
        )

    for i in range(1, 4):
        it_задача(
            company_id=companies[0],
            status="completed",
            completed_at=f"2026-09-0{i} 23:30:00",
            contractor_company_id=None if i == 3 else companies[1],
            result_url="https://www.Example.uz:8443/case?x=1" if i == 1 else None,
            result_summary="Сделали за месяц",
        )

    it_задача(closed=True, company_id=companies[0])
    it_задача(company_id=компания(status="blocked"))

    with адрес_сайта() as root:
        yield root


def лента(сайт: str, path: str, куки: dict[str, str] | None = None) -> dict[str, Any]:
    """Страница Inertia ленты: 200, свой компонент; пропсы."""
    д = открыть(сайт, path, куки)

    assert д["status"] == 200, (д["status"], д["headers"].get("location"))

    return страница(д["body"])


@pytest.mark.parametrize(
    ("path", "всего", "страница_", "на_странице", "фильтры"),
    [
        # 26 открытых: закрытая и задача заблокированной компании не видны
        ("/it-services", 26, 1, 20, {}),
        ("/it-services?page=2", 26, 2, 6, {}),
        ("/it-services?page=3", 26, 3, 0, {}),
        ("/en/it-services", 26, 1, 20, {}),
        ("/uz/it-services?page=2", 26, 2, 6, {}),
        ("/it-services?done=1", 3, 1, 3, {"done": True}),
        ("/it-services?done=yes&page=1", 3, 1, 3, {"done": True}),
        ("/it-services?done=0", 26, 1, 20, {"done": False}),
        # «склад» — во всех, кроме трёх «Sayt yaratish» (7, 14, 21)
        ("/it-services?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4", 23, 1, 20, {"q": "склад"}),
        # Латиница находит кириллицу: search_text с транслитом
        ("/it-services?q=sayt", 26, 1, 20, {"q": "sayt"}),
        ("/it-services?q=%20%20", 26, 1, 20, {"q": ""}),
        # IT — сайты, приложения, дизайн (web, mobile, design)
        ("/it-services?type=it", 13, 1, 13, {"type": "it"}),
        ("/it-services?type=hr_services", 4, 1, 4, {"type": "hr_services"}),
        (
            "/it-services?type=accounting&with_budget=on",
            4,
            1,
            4,
            {"type": "accounting", "with_budget": True},
        ),
        ("/it-services?type=nonsense", 26, 1, 20, {"type": ""}),
        # Проверенные — уровень проверки от 2
        ("/it-services?verified=true", 13, 1, 13, {"verified": True}),
        (
            "/it-services?with_budget=1&verified=1&page=2",
            8,
            2,
            0,
            {"verified": True, "with_budget": True},
        ),
        ("/it-services?city=abc", 26, 1, 20, {"city": None}),
    ],
)
def test_лента(сайт, path, всего, страница_, на_странице, фильтры):
    стр = лента(сайт, path)
    задачи = стр["props"]["tasks"]

    assert стр["component"] == "it-tasks/Index"
    assert (задачи["total"], задачи["current_page"], len(задачи["data"])) == (
        всего,
        страница_,
        на_странице,
    )
    assert задачи["last_page"] == max(1, -(-всего // 20))
    assert {k: стр["props"]["filters"][k] for k in фильтры} == фильтры
    # Выполненные — только с done, открытые — без
    assert all(t["completed"] is фильтры.get("done", False) for t in задачи["data"])


def test_фильтр_по_городу(сайт):
    города = лента(сайт, "/it-services")["props"]["cities"]

    assert города
    город = города[0]["id"]
    [(ожидание,)] = sql(
        "select count(*) from it_tasks t join companies c on c.id = t.company_id "
        "where t.status = 'active' and c.status = 'active' and c.city_id = %s",
        [город],
    )
    стр = лента(сайт, f"/tr/it-services?city={город}")

    assert стр["props"]["filters"]["city"] == город
    assert стр["props"]["tasks"]["total"] == ожидание > 0


def test_выполненные_с_исполнителем(сайт):
    задачи = лента(сайт, "/it-services?done=1")["props"]["tasks"]["data"]

    # Адрес результата — только хост, как его написали (без www и порта)
    assert [t["result_host"] for t in задачи].count("Example.uz") == 1
    assert sum(t["contractor"] is not None for t in задачи) == 2
    assert {t["result_summary"] for t in задачи} == {"Сделали за месяц"}


def test_вошедший_исполнитель(сайт):
    uid = пользователь("it@savdex.uz")
    sql(
        "update users set company_id = (select id from companies where is_it_provider "
        "order by id limit 1) where id = %s",
        [uid],
    )

    assert лента(сайт, "/it-services", вход(uid))["props"]["viewer"] == {
        "guest": False,
        "provider": True,
    }
    assert лента(сайт, "/it-services")["props"]["viewer"]["guest"] is True


def адрес(условие: str) -> str:
    return str(sql(f"select slug from it_tasks where {условие} order by id limit 1")[0][0])


def задача(сайт: str, path: str, куки: dict[str, str] | None = None) -> dict[str, Any]:
    """Карточка задачи: счётчик просмотров — с нуля перед заходом."""
    обнулить()
    д = открыть(сайт, path, куки)

    return {"status": д["status"], **(страница(д["body"]) if д["status"] == 200 else {})}


#: Размеры файлов: десятичная запятая у ru и uz, точка у en
РАЗМЕРЫ = {"": ("1,5 МБ", "1 КБ"), "/en": ("1.5 MB", "1 KB"), "/uz": ("1,5 MB", "1 KB")}


def test_страница_задачи(сайт):
    открытая = адрес("status = 'active'")
    sql(
        "insert into it_task_files (it_task_id, title, file_path, file_size, mime, created_at, "
        "updated_at) select id, t, p, s, 'application/pdf', now(), now() from it_tasks, "
        "(values ('ТЗ.PDF', 'it/a.pdf', 1536000), ('схема', 'it/b.Docx', 300), "
        "('архив.tar.gz', 'it/c', 0)) as f(t, p, s) where slug = %s",
        [открытая],
    )

    for prefix, срок in (("", "11 октября 2026"), ("/en", "11 October 2026"), ("/uz", None)):
        стр = задача(сайт, f"{prefix}/it-services/{открытая}")
        карточка = стр["props"]["task"]

        assert стр["status"] == 200 and стр["component"] == "it-tasks/Show"
        assert карточка["slug"] == открытая and карточка["active"] is True
        assert срок is None or карточка["deadline"] == срок
        # Файлы: размер по-человечески на языке страницы, расширение — из адреса
        мб, кб = РАЗМЕРЫ[prefix]
        assert [(f["title"], f["size"], f["ext"]) for f in карточка["files"]] == [
            ("ТЗ.PDF", мб, "pdf"),
            ("схема", кб, "docx"),
            ("архив.tar.gz", кб, "gz"),
        ]
        assert стр["props"]["respond"] == {
            "guest": True,
            "owner": False,
            "no_company": False,
            "provider": False,
        }
        # Просмотр гостя посчитан
        assert карточка["views"] == 1
        assert sql("select views_count from it_tasks where slug = %s", [открытая]) == [(1,)]
        assert all(s["slug"] != открытая for s in стр["props"]["similar"])

    # Выполненная с результатом и исполнителем
    выполненная = адрес("status = 'completed'")
    стр = задача(сайт, f"/zh/it-services/{выполненная}")
    карточка = стр["props"]["task"]

    assert стр["status"] == 200
    assert (карточка["active"], карточка["completed"]) == (False, True)
    assert карточка["result_host"] == "Example.uz"
    assert карточка["contractor"]["name"] == "Заказчик 1"
    assert карточка["completed_on"] == "2026年9月1日"

    # Задачи заблокированной компании нет ни в ленте, ни по прямому адресу
    чужая = адрес("company_id = (select max(id) from companies)")
    assert задача(сайт, f"/it-services/{чужая}")["status"] == 404


def обнулить() -> None:
    """Счётчик просмотров — с нуля перед каждым заходом."""
    sql("update it_tasks set views_count = 0")


def test_закрытая_видна_только_заказчику(сайт):
    закрытая = адрес("status = 'closed'")
    assert задача(сайт, f"/it-services/{закрытая}")["status"] == 404

    uid = пользователь("owner@savdex.uz")
    sql(
        "update users set company_id = (select company_id from it_tasks where slug = %s) "
        "where id = %s",
        [закрытая, uid],
    )
    стр = задача(сайт, f"/it-services/{закрытая}", вход(uid))

    assert стр["status"] == 200
    assert стр["props"]["respond"]["owner"] is True
    # Свой просмотр не считается
    assert sql("select views_count from it_tasks where slug = %s", [закрытая])[0][0] == 0


def test_нет_задачи(сайт):
    assert задача(сайт, "/it-services/nothing")["status"] == 404


def test_просмотр_администратора_в_журнале(сайт):
    uid = пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    slug = адрес("status = 'active'")
    sql("update it_tasks set views_count = 5 where slug = %s", [slug])
    sql("delete from admin_actions")

    assert открыть(сайт, f"/it-services/{slug}", вход(uid))["status"] == 200

    [д] = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb from admin_actions order by id"
    )
    [(task_id, title)] = sql("select id, title from it_tasks where slug = %s", [slug])

    assert д[:6] == (
        "Покупатель boss@savdex.uz",
        "updated",
        "ittasks",
        "App\\Models\\ItTask",
        task_id,
        title,
    )
    assert д[6]["after"]["views_count"] == 6


@pytest.fixture(scope="module")
def направления(сайт):
    """Исполнители со специализациями и опубликованные резюме — для страниц «Доп. услуг»."""
    sql(
        "update companies set it_specializations = %s, rating = 4.5 where id = "
        "(select id from companies where is_it_provider order by id limit 1)",
        ['["hr","web","erp"]'],
    )
    компания(
        name="Логист", is_it_provider=True, it_specializations=["logistics"], verification_level=2
    )
    компания(is_it_provider=True, it_specializations=["web"], status="blocked")

    for i in range(1, 4):
        sql(
            "insert into resumes (user_id, slug, title, field, experience_months, employment, "
            "status, published_at, created_at, updated_at) "
            "values (%s, %s, %s, 'sales', %s, %s, %s, %s, now(), now())",
            [
                учётка_фабрики(),
                f"cv-{i}",
                f"Менеджер {i}",
                14 * i,
                '["full"]',
                "draft" if i == 3 else "published",
                datetime(2026, 9, 1, 12, 0, 0) - timedelta(hours=i),
            ],
        )

    return сайт


@pytest.mark.parametrize(
    ("path", "раздел", "открытых", "исполнители", "резюме"),
    [
        # Исполнитель со специализацией; заблокированный — нет
        ("/services/it", "it", 13, ["Заказчик 1"], None),
        ("/services/hr", "hr_services", 4, ["Заказчик 1"], 2),
        ("/en/services/recruitment", "hr", 4, ["Заказчик 1"], 2),
        ("/services/logistics", "logistics", 5, ["Логист"], None),
        ("/uz/services/customs", "customs", 0, [], None),
        ("/zh/services/accounting", "accounting", 4, [], None),
    ],
)
def test_направление(направления, path, раздел, открытых, исполнители, резюме):
    стр = лента(направления, path)
    props = стр["props"]

    assert стр["component"] == "it-tasks/Section"
    assert props["section"]["slug"] == path.rsplit("/", 1)[1]
    # На странице — не больше шести свежих
    assert props["stats"]["active"] == открытых
    assert len(props["tasks"]) == min(открытых, 6)
    assert [p["name"] for p in props["providers"]] == исполнители
    # Резюме — только у HR: опубликованные, черновик не виден
    assert props["stats"]["resumes"] == резюме
    assert len(props["resumes"]) == (резюме or 0)
    assert props["section"]["code"] == раздел

    if path == "/services/it":
        assert props["stats"]["completed"] == len(props["completed"]) == 3
