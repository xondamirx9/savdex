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
    assert стр["component"] == "Catalog"

    return стр


@pytest.mark.parametrize(
    "path",
    [
        "/catalog?type=tender",
        "/catalog?type=tender&page=2",
        "/catalog?page=3&type=tender",
        "/en/catalog?type=tender",
        "/uz/catalog?type=tender&page=2",
        "/zh/catalog?type=tender&closed=1",
        "/tr/catalog?type=%20tender%20&closed=yes",
        "/catalog?type=tender&closed=0",
        "/catalog?type=tender&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82",
        "/catalog?type=tender&q=sement",
        "/catalog?type=tender&q=%20",
        "/catalog?type=tender&category=abc",
        "/catalog?type=tender&sort=cheap&city=5&verified=1",
    ],
)
def test_вкладка_тендеров(сайт, path):
    стр = вкладка(сайт, path)
    pr = стр["props"]
    print("DBG", path, стр["url"], {k: (v if not isinstance(v, (list, dict)) or k == "filters" else type(v).__name__ + str(len(v))) for k, v in pr.items() if k not in ("auth","bell","brandLogo","counts","errors","favorites","flash","locale","localeLinks","localeSuggest","navCategories","support","translations")})
    items = pr.get("items") or pr.get("tenders") or pr.get("results")
    if isinstance(items, dict): items = items.get("data")
    print("DBGI", [(x.get("title"), x.get("days_left"), x.get("closed")) for x in (items or [])][:30])


def test_раздел_с_подразделами(сайт):
    д, _ = сверить(сайт, "/catalog?type=tender")
    раздел = страница(д["body"])["props"]["categories"][0]["id"]
    д, _ = сверить(сайт, f"/catalog?type=tender&category={раздел}")

    # Раздел включает свой подраздел: 16 из 24 — корень и подраздел, и
    # ещё 4 открытых без срока — фабрика кладёт их в первый раздел
    assert страница(д["body"])["props"]["total"] == 20


def test_баннер_каталога(сайт):
    php(
        "App\\Models\\Banner::create(['name' => 'Тарифы', 'placement' => 'catalog',"
        "'is_active' => true,"
        "'image_path' => 'banners/c.jpg', 'url' => 'https://savdex.uz/pricing',"
        "'alt' => 'Тарифы', 'sort' => 1]);"
        "echo 'ok';"
    )
    д, _ = сверить(сайт, "/catalog?type=tender")

    assert страница(д["body"])["props"]["banner"]["alt"] == "Тарифы"


def адреса() -> list[str]:
    return [r[0] for r in sql("select slug from tenders where status = 'published' order by id")]


def test_страница_закупки(сайт):
    slugs = адреса()

    # открытая с переводом, без срока, завершённая
    for slug, prefix in ((slugs[5], ""), (slugs[5], "/en"), (slugs[25], "/uz"), (slugs[30], "/zh")):
        сверить(сайт, f"{prefix}/tenders/{slug}")


def test_нет_закупки(сайт):
    черновик = sql("select slug from tenders where status = 'draft'")[0][0]
    будущая = sql("select slug from tenders where published_at > now()")[0][0]

    for slug in ("nothing-here", черновик, будущая):
        д, _ = сверить(сайт, f"/tenders/{slug}")
        assert д["status"] == 404


def test_просмотры_считают_обе_стороны(сайт):
    slug = адреса()[2]
    было = sql("select views_count from tenders where slug = %s", [slug])[0][0]

    из_django(сайт, f"/tenders/{slug}")
    из_laravel(сайт, f"/tenders/{slug}")

    assert sql("select views_count from tenders where slug = %s", [slug])[0][0] == было + 2


def test_просмотр_администратора_в_журнале(сайт):
    пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    куки = войти(сайт, "boss@savdex.uz")
    slug = адреса()[3]
    sql("delete from admin_actions")

    из_laravel(сайт, f"/tenders/{slug}", куки)
    из_django(сайт, f"/tenders/{slug}", куки)

    строки = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb, ip from admin_actions order by id"
    )
    assert len(строки) == 2
    л, д = строки
    # До и после — на единицу больше у второй строки; остальное одинаково
    assert л[:6] == д[:6] and л[7] == д[7]
    assert д[6]["after"]["views_count"] == л[6]["after"]["views_count"] + 1
    assert д[6]["before"]["views_count"] == л[6]["after"]["views_count"]
