"""
Этап 4, шаг 4: вкладка «Тендеры» каталога (/catalog?type=tender) на
Django.

Открытые (ближайший срок сверху, без срока — в конце) и завершённые,
поиск, раздел каталога с подразделами, переводы заголовка, будущая
публикация и черновик не видны; баннер каталога; дни до конца приёма.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from .factories import Выражение, объявления, тендер
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .web_site import адрес, вход, открыть, пользователь, страница

pytestmark = нужна_база


def справочники(*таблицы: str) -> None:
    """
    Справочники из снимка savdex/bootstrap/seeds.json (savdex/seeds.py) —
    только эти таблицы, как сидеры Laravel (GeoSeeder, CategorySeeder).
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
    справочники(
        "countries",
        "country_translations",
        "cities",
        "city_translations",
        "categories",
        "category_translations",
        "category_fields",
    )

    # 24 открытых (две страницы), 4 без срока, 5 завершённых, будущая
    # публикация, черновик; часть — в подразделе, часть — с переводом
    [(uz,)] = sql("select id from countries where code = 'uz'")
    [(root,)] = sql("select id from categories where parent_id is null order by sort, id limit 1")
    [(child,)] = sql(
        "select id from categories where parent_id = %s order by sort, id limit 1", [root]
    )
    [(other,)] = sql(
        "select id from categories where parent_id is null order by sort, id offset 1 limit 1"
    )

    for i in range(1, 25):
        тендер(
            title=f"{'Поставка цемента ' if i % 5 else 'Sement yetkazib berish '}{i}",
            category_id=[root, child, other][i % 3],
            country_id=uz if i % 2 else None,
            budget=1000000 * i if i % 4 else None,
            deadline_at=Выражение(f"now() + interval '{20 * i} hours'"),
            published_at=Выражение(f"now() - interval '{i % 5} days'"),
            title_i18n=None if i % 6 else {"en": f"Cement supply {i}", "uz": " "},
            description_i18n=None if i % 6 else {"en": "Cement."},
        )

    for i in range(1, 5):
        тендер(deadline_at=None, published_at=Выражение(f"now() - interval '{i} days'"))

    for i in range(1, 6):
        тендер(deadline_at=Выражение(f"now() - interval '{i} days 3 hours'"))

    тендер(published_at=Выражение("now() + interval '1 day'"))
    тендер(draft=True)
    объявления(3)

    with адрес() as root_url:
        yield root_url


def вкладка(сайт: str, path: str) -> dict[str, Any]:
    д = открыть(сайт, path)

    assert д["status"] == 200, (д["status"], д["headers"].get("location"))
    стр = страница(д["body"])
    assert стр["component"] == "catalog/Index"

    return стр


@pytest.mark.parametrize(
    ("path", "всего", "на_странице", "завершённые", "первая"),
    [
        # Открытые: ближайший срок сверху, без срока — в конце
        ("/catalog?type=tender", 28, 20, False, "Поставка цемента 1"),
        ("/catalog?type=tender&page=2", 28, 8, False, "Поставка цемента 21"),
        ("/catalog?page=3&type=tender", 28, 0, False, None),
        # Перевод заголовка — на языке страницы
        ("/en/catalog?type=tender", 28, 20, False, "Поставка цемента 1"),
        ("/uz/catalog?type=tender&page=2", 28, 8, False, "Поставка цемента 21"),
        # Завершённые: последний закрытый сверху
        ("/zh/catalog?type=tender&closed=1", 5, 5, True, None),
        ("/tr/catalog?type=%20tender%20&closed=yes", 5, 5, True, None),
        ("/catalog?type=tender&closed=0", 28, 20, False, "Поставка цемента 1"),
        # «цемент» — двадцать «Поставка цемента …» и одна закупка фабрики
        ("/catalog?type=tender&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82", 21, 20, False, None),
        # Латиница находит и кириллицу (транслит в search_text)
        ("/catalog?type=tender&q=sement", 25, 20, False, None),
        ("/catalog?type=tender&q=%20", 28, 20, False, None),
        ("/catalog?type=tender&category=abc", 28, 20, False, None),
        # Сортировка, город и «проверенные» у закупок не действуют
        ("/catalog?type=tender&sort=cheap&city=5&verified=1", 28, 20, False, None),
    ],
)
def test_вкладка_тендеров(сайт, path, всего, на_странице, завершённые, первая):
    стр = вкладка(сайт, path)
    props = стр["props"]
    закупки = props["tenders"]["data"]

    assert props["filters"]["type"] == "tender"
    assert props["filters"]["closed"] is завершённые
    assert (props["total"], props["tenders"]["total"], len(закупки)) == (всего, всего, на_странице)
    assert all(t["closed"] is завершённые for t in закупки)
    assert первая is None or закупки[0]["title"] == первая

    сроки = [t["days_left"] for t in закупки]
    сроки_есть = [d for d in сроки if d is not None]

    if завершённые:
        # Приём закончился: дней — меньше нуля, последний закрытый сверху
        assert all(d < 0 for d in сроки) and сроки == sorted(сроки, reverse=True)
    else:
        # Ближайший срок сверху; без срока — только в конце
        assert сроки_есть == sorted(сроки_есть)
        assert сроки[: len(сроки_есть)] == сроки_есть


def test_перевод_заголовка(сайт):
    """Свой перевод — на своём языке; пустой перевод — исходный заголовок."""
    en = {t["title"] for t in вкладка(сайт, "/en/catalog?type=tender")["props"]["tenders"]["data"]}
    uz = {t["title"] for t in вкладка(сайт, "/uz/catalog?type=tender")["props"]["tenders"]["data"]}

    assert {"Cement supply 6", "Cement supply 12", "Cement supply 18"} <= en
    assert "Поставка цемента 6" not in en
    assert "Поставка цемента 6" in uz


def test_раздел_с_подразделами(сайт):
    раздел = вкладка(сайт, "/catalog?type=tender")["props"]["categories"][0]["id"]
    стр = вкладка(сайт, f"/catalog?type=tender&category={раздел}")

    # Раздел включает свой подраздел: 16 из 24 — корень и подраздел, и
    # ещё 4 открытых без срока — фабрика кладёт их в первый раздел
    assert стр["props"]["filters"]["category"] == раздел
    assert стр["props"]["total"] == 20


def test_баннер_каталога(сайт):
    sql(
        "insert into banners (name, placement, is_active, image_path, url, alt, sort, "
        "created_at, updated_at) values ('Тарифы', 'catalog', true, 'banners/c.jpg', "
        "'https://savdex.uz/pricing', 'Тарифы', 1, now(), now())"
    )
    баннер = вкладка(сайт, "/catalog?type=tender")["props"]["banner"]

    assert баннер["alt"] == "Тарифы" and баннер["url"] == "https://savdex.uz/pricing"


def адреса() -> list[str]:
    return [r[0] for r in sql("select slug from tenders where status = 'published' order by id")]


def test_страница_закупки(сайт):
    slugs = адреса()

    # открытая с переводом, без срока, завершённая:
    # (адрес, язык, заголовок, описание, месяц срока, завершена)
    for slug, prefix, заголовок, описание, месяц, завершена in (
        (slugs[5], "", "Поставка цемента 6", None, "{d.day} {ru}", False),
        (slugs[5], "/en", "Cement supply 6", ["Cement."], "{d.day} {en}", False),
        (slugs[25], "/uz", None, None, None, False),
        (slugs[30], "/zh", None, None, "{d.day}", True),
    ):
        д = открыть(сайт, f"{prefix}/tenders/{slug}")
        стр = страница(д["body"])
        закупка = стр["props"]["tender"]
        [(срок,)] = sql("select deadline_at from tenders where slug = %s", [slug])

        assert д["status"] == 200 and стр["component"] == "tenders/Show"
        assert закупка["slug"] == slug and закупка["closed"] is завершена
        assert заголовок is None or закупка["title"] == заголовок
        assert описание is None or закупка["description"] == описание

        if месяц is None:
            # Без срока — ни даты, ни дней
            assert (закупка["deadline"], закупка["days_left"]) == (None, None)
        else:
            # Дата — по-человечески на языке страницы: «6 октября 2026»
            # (срок в базе — UTC; день берём и по UTC, и по Ташкенту)
            подписи = {
                месяц.format(d=d, ru=МЕСЯЦЫ[d.month - 1], en=d.strftime("%B")) + " "
                for d in (срок, срок + timedelta(hours=5))
            }
            assert any(закупка["deadline"].startswith(p) for p in подписи), закупка["deadline"]
            assert закупка["deadline"].endswith(str(срок.year))
            # Ровно пять суток до срока у открытой; у завершённой — меньше нуля
            assert закупка["days_left"] < 0 if завершена else закупка["days_left"] == 5

        # Похожие — открытые закупки того же раздела, без самой этой
        assert стр["props"]["similar"]
        assert all(not t["closed"] and t["slug"] != slug for t in стр["props"]["similar"])


МЕСЯЦЫ = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def test_нет_закупки(сайт):
    черновик = sql("select slug from tenders where status = 'draft'")[0][0]
    будущая = sql("select slug from tenders where published_at > now()")[0][0]

    for slug in ("nothing-here", черновик, будущая):
        assert открыть(сайт, f"/tenders/{slug}")["status"] == 404


def test_просмотры_считаются(сайт):
    slug = адреса()[2]
    было = sql("select views_count from tenders where slug = %s", [slug])[0][0]

    assert открыть(сайт, f"/tenders/{slug}")["status"] == 200
    assert открыть(сайт, f"/tenders/{slug}")["status"] == 200

    assert sql("select views_count from tenders where slug = %s", [slug])[0][0] == было + 2


def test_просмотр_администратора_в_журнале(сайт):
    uid = пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    куки = вход(uid)
    slug = адреса()[3]
    [(tid, title, было)] = sql("select id, title, views_count from tenders where slug = %s", [slug])
    sql("delete from admin_actions")

    assert открыть(сайт, f"/tenders/{slug}", куки)["status"] == 200
    assert открыть(сайт, f"/tenders/{slug}", куки)["status"] == 200

    строки = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb, ip from admin_actions order by id"
    )
    assert len(строки) == 2
    первая, вторая = строки
    # Строка на каждый просмотр: до и после — на единицу больше у второй
    assert первая[:6] == вторая[:6]
    assert первая[1:6] == ("updated", "tenders", "App\\Models\\Tender", tid, title)
    assert первая[6]["after"]["views_count"] == было + 1
    assert вторая[6]["before"]["views_count"] == было + 1
    assert вторая[6]["after"]["views_count"] == было + 2
