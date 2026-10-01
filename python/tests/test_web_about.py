"""
«О компании» и «Контакты» — проверки Django (этап 3).

«О компании»: счётчики витрины из базы (на всех языках одни и те же —
и с загруженными из книги объявлениями без перевода), тексты из админки, офис на
карте и его разметка для поисковика, оглавление. «Контакты» — страница
без своих данных, только общие.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .factories import компания, объявление, объявления
from .pg_admin import sql, нужна_база, свежая_база
from .web_site import адрес, открыть, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    # Шесть объявлений — шесть действующих компаний; черновик и
    # заблокированная компания в счётчики не входят
    объявления(3)
    объявление(source="import", title_i18n={"uz": "X"})
    объявление(source="import", title_i18n=None)
    объявление(draft=True)
    компания(status="blocked")

    with адрес() as root:
        yield root


@pytest.mark.parametrize(
    ("path", "locale"), [("/about", "ru"), ("/uz/about", "uz"), ("/en/about", "en")]
)
def test_без_офиса(сайт, path, locale):
    д = открыть(сайт, path)
    стр = страница(д["body"])

    assert д["status"] == 200 and стр["component"] == "About" and стр["url"] == path
    assert стр["props"]["locale"] == locale
    assert стр["props"]["office"] is None
    nav = [n["key"] for n in стр["props"]["nav"]]
    assert nav == ["about", "contacts", "help", "guide", "rules"]
    assert стр["props"]["stats"]["companies"] == 6


@pytest.mark.parametrize(("path", "locale"), [("/contact", "ru"), ("/zh/contact", "zh")])
def test_контакты(сайт, path, locale):
    д = открыть(сайт, path)
    стр = страница(д["body"])

    assert д["status"] == 200 and стр["component"] == "Contacts" and стр["url"] == path
    assert стр["props"]["locale"] == locale
    # Своих данных нет — только общие
    assert not {"stats", "office", "nav", "page"} & set(стр["props"])


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

    д = открыть(сайт, "/about")
    props = страница(д["body"])["props"]
    assert props["office"]["zoom"] == 19
    assert props["office"]["address"] == "Ташкент, ул. Амира Темура, 1"
    assert [n["key"] for n in props["nav"]][:3] == ["about", "contacts", "office"]
    assert "О площадке SAVDEX" in д["body"]
    # Офис — и в разметке для поисковика
    assert "Амира Темура" in д["body"] and "41.311081" in д["body"]

    tr = страница(открыть(сайт, "/tr/about")["body"])["props"]
    assert tr["locale"] == "tr" and tr["office"] == props["office"]


def test_счётчики(сайт):
    д = открыть(сайт, "/uz/about")
    ru = открыть(сайт, "/about")

    # Загруженное из книги без перевода видно на всех языках (94778c4):
    # счётчик тот же, что на русской витрине
    assert (
        страница(ru["body"])["props"]["stats"]["listings"]
        == страница(д["body"])["props"]["stats"]["listings"]
        == 5
    )
