"""
Раздел «Главная страница» админки на Django — сквозь настоящую базу и сайт.

Секции главной заводит снимок схемы (миграция
2026_09_28_180000_landing_from_dictionaries) — с текстами на всех
языках, какими их показывал сайт. Проверяется то, ради чего раздел
устроен именно так:

- у секции только её поля, правка доходит до сайта;
- пункты «Как это работает» и «Частых вопросов» проверяются: вопрос
  без ответа не сохраняется;
- секцию можно скрыть, первый экран — нельзя;
- секции не заводятся и не удаляются.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from savdex.site.landing_admin import LANDING_FIELDS

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

LIST = "/py/admin/site/landingblock/"
LANGS = ("uz", "en", "zh", "tr")
FIELDS = ("eyebrow", "heading", "subheading", "button", "body")


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("content_manager", "sales")}


def _block(key: str) -> dict[str, Any]:
    columns = ", ".join(f"{f}, {f}_i18n::text" for f in FIELDS)
    [row] = sql(f"select id, is_visible, {columns} from landing_blocks where key = %s", [key])
    block: dict[str, Any] = {"id": row[0], "visible": row[1]}

    for i, field in enumerate(FIELDS):
        block[field] = row[2 + 2 * i]
        block[f"{field}_i18n"] = json.loads(row[3 + 2 * i]) if row[3 + 2 * i] else {}

    return block


def _форма(key: str, **поля: Any) -> dict[str, Any]:
    """Форма секции как её отправляет браузер: всё, что сейчас в базе."""
    block = _block(key)
    data: dict[str, Any] = {}

    for field in LANDING_FIELDS[key]:
        data[field] = block[field] or ""

        for code in LANGS:
            data[f"{field}_{code}"] = block[f"{field}_i18n"].get(code, "")

    if block["visible"] and key != "hero":
        data["is_visible"] = "on"

    data.update(поля)

    return {k: v for k, v in data.items() if v is not None}


def _сохранить(
    люди: dict[str, int], key: str, **поля: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"{LIST}{_block(key)['id']}/change/"
    _, ответ, список = django(
        люди["content_manager"], ("post", url, _форма(key, **поля)), ("get", LIST, None)
    )

    return ответ, список


def _card(key: str, locale: str = "ru") -> dict[str, Any]:
    """Секция, как её показывает главная сайта на этом языке (проп blocks)."""
    with адрес() as сайт:
        ответ = открыть(сайт, "/" if locale == "ru" else f"/{locale}")

    assert ответ["status"] == 200
    page = страница(ответ["body"])
    assert page["component"] == "Home"

    return dict(page["props"]["blocks"][key])


def test_миграция_перенесла_секции_макета(люди):
    keys = [key for (key,) in sql("select key from landing_blocks order by sort")]

    assert keys == list(LANDING_FIELDS)
    assert _block("hero")["heading"] == "Поставщики и закупщики находят друг друга"
    assert len(_card("faq")["items"]) == 6


def test_список_и_права(люди):
    _, список, добавить = django(
        люди["content_manager"], ("get", LIST, None), ("get", f"{LIST}add/", None)
    )

    assert список["status"] == 200
    for name in ("Первый экран", "Как это работает", "Частые вопросы", "Призыв в конце"):
        assert name in список["body"]
    assert добавить["status"] == 403

    _, удалить = django(
        люди["content_manager"], ("post", f"{LIST}{_block('news')['id']}/delete/", {"post": "yes"})
    )
    assert удалить["status"] == 403

    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_у_секции_только_её_поля(люди):
    _, поставщики, счётчики = django(
        люди["content_manager"],
        ("get", f"{LIST}{_block('suppliers')['id']}/change/", None),
        ("get", f"{LIST}{_block('stats')['id']}/change/", None),
    )

    assert 'name="heading"' in поставщики["body"]
    assert 'name="body"' not in поставщики["body"]
    assert 'name="button"' not in поставщики["body"]
    assert 'name="heading"' not in счётчики["body"]
    assert 'name="is_visible"' in счётчики["body"]


def test_правка_доходит_до_сайта_и_в_журнал(люди):
    ответ, _ = _сохранить(люди, "hero", heading="Новый заголовок", heading_uz="Yangi sarlavha")

    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _card("hero")["heading"] == "Новый заголовок"
    assert _card("hero", "uz")["heading"] == "Yangi sarlavha"

    запись = журнал("updated")
    assert запись["section"] == "content"
    assert запись["subject_type"] == "App\\Models\\LandingBlock"
    assert запись["changes"]["after"]["heading"] == "Новый заголовок"


def test_вопрос_без_ответа_не_сохраняется(люди):
    before = _block("faq")["body"]
    ответ, _ = _сохранить(люди, "faq", body="Можно ли по счёту?\nДа.\n\nА без ответа?")

    assert ответ["status"] == 200
    assert "У пункта «А без ответа?» нет пояснения" in ответ["body"]
    assert _block("faq")["body"] == before

    ответ, _ = _сохранить(
        люди,
        "faq",
        body="Можно ли по счёту?\nДа, для юрлиц.",
        **{f"body_{code}": "" for code in LANGS},
    )
    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _card("faq")["items"] == [{"title": "Можно ли по счёту?", "text": "Да, для юрлиц."}]


def test_скрыть_секцию_но_не_первый_экран(люди):
    ответ, _ = _сохранить(люди, "reviews", is_visible=None)
    assert ответ["status"] == 302, ответ["body"][:3000]
    assert _block("reviews")["visible"] is False
    assert _card("reviews")["visible"] is False

    _, форма = django(
        люди["content_manager"], ("get", f"{LIST}{_block('hero')['id']}/change/", None)
    )
    assert 'name="is_visible"' not in форма["body"]

    _сохранить(люди, "hero")
    assert _block("hero")["visible"] is True


def test_пустой_заголовок_не_сохраняется(люди):
    ответ, _ = _сохранить(люди, "vip", heading="")

    assert ответ["status"] == 200
    assert "Обязательное поле." in ответ["body"]


def test_предупреждение_о_прежнем_переводе(люди):
    _, список = _сохранить(люди, "news", heading="Что нового на площадке")

    assert "Русский текст изменён, а свой перевод остался прежним" in список["body"]

    # Очищенный язык — машинный перевод русского
    _сохранить(люди, "news", heading_en="")
    assert "en" not in _block("news")["heading_i18n"]
    assert _card("news", "en")["heading"] == "Что нового на площадке"
    assert sql(
        "select count(*) from content_translations where locale = 'en' and source = %s",
        ["Что нового на площадке"],
    ) == [(1,)]
