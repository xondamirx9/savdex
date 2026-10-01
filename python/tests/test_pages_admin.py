"""
Раздел «Страницы и FAQ» админки на Django — сквозь настоящую базу и
страницы сайта.

Страницы и вопросы помощи заводит миграция
(2026_09_28_160000_pages_from_dictionaries, в снимке схемы) — с текстами
на всех языках, какими их показывал сайт. Проверяется то, ради чего раздел
устроен именно так:

- правка доходит до сайта, в том числе свой текст языка;
- очищенный язык сайт показывает машинным переводом;
- русский текст поменяли, а свой перевод оставили — раздел
  предупреждает;
- вопросы помощи правятся вместе со страницей и попадают в журнал;
- страницы не заводятся и не удаляются, «О компании» не скрывается.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник
from .web_site import адрес, открыть, страница

pytestmark = нужна_база

LIST = "/py/admin/site/page/"
LANGS = ("uz", "en", "zh", "tr")


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("content_manager", "sales")}


@pytest.fixture(scope="module")
def сайт(люди) -> Iterator[str]:
    with адрес() as root:
        yield root


def на_сайте(сайт: str, path: str) -> dict[str, Any]:
    """Пропсы страницы сайта (About или DocPage)."""
    д = открыть(сайт, path)
    assert д["status"] == 200, д["status"]

    return dict(страница(д["body"])["props"])


def _page(key: str) -> dict[str, Any]:
    [row] = sql(
        "select id, title, excerpt, body, title_i18n::text, excerpt_i18n::text, body_i18n::text, "
        "is_published from pages where key = %s",
        [key],
    )
    keys = (
        "id",
        "title",
        "excerpt",
        "body",
        "title_i18n",
        "excerpt_i18n",
        "body_i18n",
        "published",
    )
    page = dict(zip(keys, row, strict=True))

    for column in ("title_i18n", "excerpt_i18n", "body_i18n"):
        page[column] = json.loads(page[column]) if page[column] else {}

    return page


def _форма(key: str, **поля: Any) -> dict[str, Any]:
    """Форма страницы как её отправляет браузер: всё, что сейчас в базе."""
    page = _page(key)
    data: dict[str, Any] = {
        "title": page["title"],
        "excerpt": page["excerpt"] or "",
        "body": page["body"] or "",
        "meta_title": "",
        "meta_description": "",
    }

    if page["published"] and key in ("help", "guide", "rules"):
        data["is_published"] = "on"

    for column in ("title", "excerpt", "body"):
        for code in LANGS:
            data[f"{column}_{code}"] = page[f"{column}_i18n"].get(code, "")

    if key == "help":
        data.update(_вопросы(page["id"]))

    data.update(поля)

    return {k: v for k, v in data.items() if v is not None}


def _вопросы(page_id: int) -> dict[str, Any]:
    rows = sql(
        "select id, question, answer, question_i18n::text, answer_i18n::text, sort, is_published "
        "from faq_items where page_id = %s order by sort, id",
        [page_id],
    )
    data: dict[str, Any] = {
        "faq_items-TOTAL_FORMS": str(len(rows)),
        "faq_items-INITIAL_FORMS": str(len(rows)),
        "faq_items-MIN_NUM_FORMS": "0",
        "faq_items-MAX_NUM_FORMS": "1000",
    }

    for i, (pk, question, answer, q_i18n, a_i18n, sort, published) in enumerate(rows):
        q_i18n, a_i18n = json.loads(q_i18n or "{}"), json.loads(a_i18n or "{}")
        data |= {
            f"faq_items-{i}-id": str(pk),
            f"faq_items-{i}-page": str(page_id),
            f"faq_items-{i}-question": question,
            f"faq_items-{i}-answer": answer,
            f"faq_items-{i}-sort": str(sort),
        }

        if published:
            data[f"faq_items-{i}-is_published"] = "on"

        for code in LANGS:
            data[f"faq_items-{i}-question_{code}"] = q_i18n.get(code, "")
            data[f"faq_items-{i}-answer_{code}"] = a_i18n.get(code, "")

    return data


def _сохранить(люди: dict[str, int], key: str, **поля: Any) -> dict[str, Any]:
    url = f"{LIST}{_page(key)['id']}/change/"
    _, ответ, список = django(
        люди["content_manager"], ("post", url, _форма(key, **поля)), ("get", LIST, None)
    )
    assert ответ["status"] == 302, ответ["body"][:3000]

    return список


def test_миграция_перенесла_тексты_сайта(люди):
    rules = _page("rules")

    assert rules["title"] == "Правила размещения"
    assert rules["body"].startswith("! Контактные данные в тексте объявления запрещены.")
    assert rules["title_i18n"]["uz"] == "Joylashtirish qoidalari"
    assert sql("select count(*) from faq_items") == [(5,)]


def test_список_и_права(люди):
    _, список, добавить = django(
        люди["content_manager"], ("get", LIST, None), ("get", f"{LIST}add/", None)
    )

    assert список["status"] == 200
    for title in ("О компании", "Контакты", "Помощь", "Инструкция использования"):
        assert title in список["body"]
    assert 'href="/help"' in список["body"]
    # Набор страниц задан кодом сайта
    assert добавить["status"] == 403
    assert f"{LIST}add/" not in список["body"]

    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_правка_доходит_до_сайта_и_в_журнал(люди, сайт):
    _сохранить(люди, "about", excerpt="Новый подзаголовок", excerpt_uz="Yangi sarlavha")

    assert на_сайте(сайт, "/about")["page"]["lead"] == "Новый подзаголовок"
    assert на_сайте(сайт, "/uz/about")["page"]["lead"] == "Yangi sarlavha"

    запись = журнал("updated")
    assert запись["section"] == "content"
    assert запись["subject_type"] == "App\\Models\\Page"
    assert запись["changes"]["after"]["excerpt"] == "Новый подзаголовок"


def test_очищенный_язык_уходит_в_машинный_перевод(люди, сайт):
    _сохранить(люди, "guide", title_en="")

    assert "en" not in _page("guide")["title_i18n"]
    # Перевода ещё нет: сайт показывает русский и ставит текст в очередь
    assert на_сайте(сайт, "/en/guide")["page"]["title"] == "Инструкция использования"
    assert sql(
        "select count(*) from content_translations where locale = 'en' and source = %s",
        ["Инструкция использования"],
    ) == [(1,)]


def test_предупреждение_о_прежнем_переводе(люди):
    список = _сохранить(люди, "rules", title="Правила публикации")

    assert "Русский текст изменён, а свой перевод остался прежним" in список["body"]
    assert "O‘zbekcha" in список["body"]

    # Перевод обновили вместе с русским — предупреждать не о чем
    список = _сохранить(
        люди,
        "rules",
        title="Правила",
        **{f"title_{code}": "" for code in LANGS},
    )
    assert "свой перевод остался прежним" not in список["body"]


def test_о_компании_не_скрывается_а_инструкция_скрывается(люди, сайт):
    _, форма = django(
        люди["content_manager"], ("get", f"{LIST}{_page('about')['id']}/change/", None)
    )
    assert 'name="is_published"' not in форма["body"]

    _сохранить(люди, "about", is_published=None)
    assert _page("about")["published"] is True

    _сохранить(люди, "help", is_published=None)
    assert _page("help")["published"] is False
    # Скрытую страницу сайт не показывает, «О компании» — на месте
    assert открыть(сайт, "/help")["status"] == 404
    assert на_сайте(сайт, "/about")["page"]["key"] == "about"
    _сохранить(люди, "help", is_published="on")
    assert на_сайте(сайт, "/help")["page"]["key"] == "help"


def test_удалить_страницу_нельзя(люди):
    _, удаление = django(
        люди["content_manager"],
        ("post", f"{LIST}{_page('contacts')['id']}/delete/", {"post": "yes"}),
    )

    assert удаление["status"] == 403
    assert sql("select count(*) from pages where key = 'contacts'") == [(1,)]


def test_вопросы_помощи(люди, сайт):
    help_id = _page("help")["id"]
    form = _форма("help")
    n = int(form["faq_items-TOTAL_FORMS"])

    # Новый вопрос со своим переводом, первый — убрать
    form |= {
        "faq_items-TOTAL_FORMS": str(n + 1),
        f"faq_items-{n}-question": "Можно ли оплатить по счёту?",
        f"faq_items-{n}-answer": "Да, для юрлиц.",
        f"faq_items-{n}-question_uz": "Hisob bo‘yicha to‘lash mumkinmi?",
        f"faq_items-{n}-sort": "9",
        f"faq_items-{n}-is_published": "on",
        "faq_items-0-DELETE": "on",
    }
    _, ответ = django(люди["content_manager"], ("post", f"{LIST}{help_id}/change/", form))
    assert ответ["status"] == 302, ответ["body"][:3000]

    rows = sql(
        "select question, question_i18n::text from faq_items where page_id = %s order by sort, id",
        [help_id],
    )
    assert len(rows) == n
    assert rows[-1][0] == "Можно ли оплатить по счёту?"
    assert json.loads(rows[-1][1]) == {"uz": "Hisob bo‘yicha to‘lash mumkinmi?"}
    assert "Сколько стоит разместить объявление?" not in [q for q, _ in rows]

    # Сайт видит новый вопрос, и по-узбекски — своим текстом
    вопросы = [f["question"] for f in на_сайте(сайт, "/uz/help")["faq"]]
    assert "Hisob bo‘yicha to‘lash mumkinmi?" in вопросы
    assert len(вопросы) == n

    # Вопросы — часть страницы: их правка в журнале страницы
    запись = журнал("updated")
    assert запись["subject_type"] == "App\\Models\\Page"
    assert "faq" in запись["changes"]["after"]
