"""
Ссылка для MEYOS (savdex/data/meyos.py).

- по умолчанию выключена: /feeds/meyos.json — 404 и с любым ключом;
- «Включить» выдаёт ключ; по ссылке — опубликованные мебельные
  объявления (раздел «Мебель» и мебельные слова), без контактов;
- чужой ключ — 404; «Выдать новую ссылку» — прежняя перестаёт работать;
- «Скачать JSON» — тот же список файлом, и при выключенной ссылке;
- страница — у кого integrations.view, кнопки — integrations.edit;
  каждое действие — строка журнала, ключа в журнале нет.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

PAGE = "/py/admin/integrations/meyos/"
FEED = "/feeds/meyos.json"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator", "sales")}


@pytest.fixture(autouse=True)
def чисто(люди) -> None:
    sql("delete from listing_images")
    sql("delete from listings")
    sql("delete from companies")
    sql("delete from category_translations")
    sql("delete from categories")
    sql("delete from settings where key like 'meyos%%'")
    sql("delete from admin_actions where section in ('integrations', 'listings')")


def _категория(slug: str, name: str, parent: int | None = None) -> int:
    [(pk,)] = sql(
        "insert into categories (slug, parent_id, sort, is_active, created_at, updated_at) "
        "values (%s, %s, 0, true, now(), now()) returning id",
        [slug, parent],
    )
    sql(
        "insert into category_translations (category_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', %s, now(), now())",
        [pk, name],
    )

    return int(pk)


def _объявление(title: str, category: int, status: str = "active") -> int:
    [(company,)] = sql(
        "insert into companies (name, slug, status, phone, email, created_at, updated_at) "
        "values ('Мебель Плюс', 'co-' || nextval('companies_id_seq'), 'active', "
        "'+998901234567', 'sales@example.com', now(), now()) returning id"
    )
    [(pk,)] = sql(
        "insert into listings (company_id, title, slug, type, status, currency, price, "
        "category_id, published_at, created_at, updated_at) values (%s, %s, "
        "'l-' || nextval('listings_id_seq'), 'supply', %s, 'UZS', 1500000, %s, now(), now(), "
        "now()) returning id",
        [company, title, status, category],
    )

    return int(pk)


def _каталог() -> None:
    мебель = _категория("mebel", "Мебель")
    дом = _категория("mebel-dlya-doma", "Мебель для дома", мебель)
    бетон = _категория("cement-beton", "Цемент и бетон")
    _объявление("Диван угловой", дом)
    _объявление("Шкаф на проверке", дом, status="moderation")
    _объявление("ЛДСП Egger 16 мм", бетон)
    _объявление("Цемент М400", бетон)


def _ключ() -> str:
    rows = sql("select value::text from settings where key = 'meyos_feed_key'")

    return json.loads(rows[0][0]) if rows else ""


def _лента(uid: int, key: str) -> dict[str, Any]:
    _, ответ = django(uid, ("get", f"{FEED}?key={key}", None))

    return ответ


def _act(uid: int, act: str) -> dict[str, Any]:
    _, ответ = django(uid, ("post", PAGE, {"act": act}))

    return ответ


def test_выключена_по_умолчанию(люди):
    _каталог()

    _, страница = django(люди["admin"], ("get", PAGE, None))
    ответ = _лента(люди["admin"], "любой")

    assert страница["status"] == 200 and "выключена" in страница["body"]
    assert "Сейчас таких объявлений: <b>2</b>" in страница["body"]
    assert ответ["status"] == 404


def test_включить_и_забрать(люди):
    _каталог()

    assert _act(люди["admin"], "enable")["status"] == 302
    ключ = _ключ()
    ответ = _лента(люди["admin"], ключ)
    чужой = _лента(люди["admin"], ключ[:-2] + "xx")

    assert len(ключ) >= 30
    assert ответ["status"] == 200 and чужой["status"] == 404
    data = json.loads(ответ["body"])
    assert data["source"] == "savdex.uz" and data["count"] == 2
    assert {item["title"] for item in data["items"]} == {"Диван угловой", "ЛДСП Egger 16 мм"}
    assert "+998901234567" not in ответ["body"] and "sales@example.com" not in ответ["body"]
    assert all(item["url"] for item in data["items"])
    assert "admin_url" not in data["items"][0] and "status" not in data["items"][0]

    строка = журнал("updated")
    assert строка["section"] == "integrations"
    assert ключ not in json.dumps(строка["changes"], ensure_ascii=False)


def test_новая_ссылка_и_выключение(люди):
    _act(люди["admin"], "enable")
    прежний = _ключ()

    _act(люди["admin"], "regenerate")
    новый = _ключ()

    assert новый != прежний
    assert _лента(люди["admin"], прежний)["status"] == 404
    assert _лента(люди["admin"], новый)["status"] == 200

    _act(люди["admin"], "disable")
    assert _лента(люди["admin"], новый)["status"] == 404
    notes = [
        n
        for (n,) in sql("select note from admin_actions where section = 'integrations' order by id")
    ]
    assert notes == [
        "Ссылка для MEYOS включена",
        "Выдана новая ссылка для MEYOS, прежняя не работает",
        "Ссылка для MEYOS выключена",
    ]


def test_скачать_файлом_и_при_выключенной(люди):
    _каталог()

    _, ответ = django(люди["admin"], ("post", PAGE, {"act": "download"}))

    assert ответ["status"] == 200
    assert json.loads(ответ["body"])["count"] == 2
    [(note,)] = sql("select note from admin_actions where action = 'exported'")
    assert note == "Для MEYOS: мебельные объявления, JSON, 2 шт."


def test_права(люди):
    _, модератор = django(люди["moderator"], ("get", PAGE, None))
    _, продавец = django(люди["sales"], ("post", PAGE, {"act": "enable"}))
    _, окно = django(люди["admin"], ("get", "/py/admin/data/listing/", None))

    assert модератор["status"] == 403 and продавец["status"] == 403
    assert _ключ() == ""
    assert PAGE in окно["body"], "из окна «Выгрузка» — ссылка на страницу MEYOS"
