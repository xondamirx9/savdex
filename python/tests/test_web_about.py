"""
«О компании» и «Контакты» на Django неотличимы от Laravel (этап 3).

«О компании»: счётчики витрины из базы (на других языках — без
импортированных объявлений без перевода), тексты из админки, офис на
карте и его разметка для поисковика, оглавление. «Контакты» — страница
без своих данных, только общие.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база
from .web_site import laravel, сверить, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Listing::factory()->count(3)->create();"
        "App\\Models\\Listing::factory()"
        "->create(['source' => 'import', 'title_i18n' => ['uz' => 'X']]);"
        "App\\Models\\Listing::factory()->create(['source' => 'import', 'title_i18n' => null]);"
        "App\\Models\\Listing::factory()->draft()->create();"
        "App\\Models\\Company::factory()->create(['status' => 'blocked']);"
        "echo 'ok';"
    )

    with laravel() as root:
        yield root


@pytest.mark.parametrize("path", ["/about", "/uz/about", "/en/about", "/contact", "/zh/contact"])
def test_без_офиса(сайт, path):
    сверить(сайт, path)


def test_с_офисом_и_своим_заголовком(сайт):
    sql(
        'insert into settings (key, label, "group", type, value, sort, created_at, updated_at) '
        "values ('office_address', 'Адрес', 'contacts', 'string', "
        "'\"Ташкент, ул. Амира Темура, 1\"', "
        "0, now(), now()), ('office_coords', 'Точка', 'contacts', 'string', "
        "'\"41.311081, 69.240562\"', 0, now(), now()), ('office_map_zoom', 'Масштаб', 'contacts', "
        "'number', '25', 0, now(), now()) on conflict (key) do update set value = excluded.value"
    )
    sql("update pages set meta_title = 'О площадке SAVDEX' where key = 'about'")

    д, _ = сверить(сайт, "/about")
    props = страница(д["body"])["props"]
    assert props["office"]["zoom"] == 19
    assert [n["key"] for n in props["nav"]][:3] == ["about", "contacts", "office"]

    сверить(сайт, "/tr/about")


def test_счётчики(сайт):
    д, _ = сверить(сайт, "/uz/about")
    ru, _ = сверить(сайт, "/about")

    # Импортированное без перевода не видно на узбекской витрине
    assert (
        страница(ru["body"])["props"]["stats"]["listings"] - 1
        == страница(д["body"])["props"]["stats"]["listings"]
    )
