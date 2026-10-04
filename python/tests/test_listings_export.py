"""
Окно «Выгрузка» в разделе «Объявления» (savdex/data/listing_export.py).

- формат Excel, CSV или JSON; категории — раздел вместе с подразделами;
- «Мебель и всё, что с ней связано»: раздел «Мебель» плюс объявления
  других категорий с мебельными словами в заголовке — с начала слова,
  список слов — настройка furniture_keywords;
- статус (опубликованные или все, кроме корзины) и тип;
- в каждой строке — ссылки на сайте и в админке, контактов продавца нет;
- старая выгрузка «как на экране» (без pick=1) работает и в JSON;
- строка журнала «Выгрузка» говорит, что выгрузили.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import pytest

from savdex.data.listing_export import parse_keywords

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

EXPORT = "/py/admin/data/listing/export/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "moderator")}


@pytest.fixture(autouse=True)
def чисто(люди) -> None:
    sql("delete from listing_images")
    sql("delete from listings")
    sql("delete from companies")
    sql("delete from category_translations")
    sql("delete from categories")
    sql("delete from settings where key = 'furniture_keywords'")
    sql("delete from admin_actions where section = 'listings'")


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


def _каталог() -> dict[str, int]:
    мебель = _категория("mebel", "Мебель")
    стройка = _категория("stroymaterialy", "Стройматериалы")

    return {
        "мебель": мебель,
        "офис": _категория("ofisnaya-mebel", "Офисная мебель", мебель),
        "дом": _категория("mebel-dlya-doma", "Мебель для дома", мебель),
        "стройка": стройка,
        "бетон": _категория("cement-beton", "Цемент и бетон", стройка),
    }


def _компания(name: str = "Мебель Плюс") -> int:
    [(pk,)] = sql(
        "insert into companies (name, slug, status, phone, email, created_at, updated_at) "
        "values (%s, 'co-' || nextval('companies_id_seq'), 'active', '+998901234567', "
        "'sales@example.com', now(), now()) returning id",
        [name],
    )

    return int(pk)


def _объявление(title: str, category: int, status: str = "active", **поля: Any) -> int:
    строка = {
        "company_id": поля.pop("company_id", None) or _компания(),
        "title": title,
        "slug": "l-" + str(abs(hash(title)))[:10],
        "type": "supply",
        "status": status,
        "currency": "UZS",
        "price": 1500000,
        "category_id": category,
        **поля,
    }
    columns = list(строка)
    [(pk,)] = sql(
        f"insert into listings ({', '.join(columns)}, published_at, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now(), now()) returning id",
        list(строка.values()),
    )

    return int(pk)


def _json(uid: int, query: str) -> dict[str, Any]:
    _, ответ = django(uid, ("get", EXPORT + query, None))
    assert ответ["status"] == 200, ответ["body"][:500]

    return json.loads(ответ["body"])


def _заголовки(data: dict[str, Any]) -> set[str]:
    return {item["title"] for item in data["items"]}


def test_слова_из_настройки():
    assert parse_keywords("ДСП, фурнитур\nстолешниц;; Мебел!") == [
        "дсп",
        "фурнитур",
        "столешниц",
        "мебел",
    ]
    assert parse_keywords("") == []


# ── Выгрузка из окна ────────────────────────────────────────────────


def test_мебель_и_всё_связанное(люди):
    к = _каталог()
    _объявление("Офисный стол руководителя", к["офис"])
    _объявление("Диван угловой", к["дом"])
    _объявление("Шкаф-купе на проверке", к["дом"], status="moderation")
    _объявление("ЛДСП Egger 16 мм", к["бетон"])
    _объявление("Столбы бетонные", к["бетон"])
    _объявление("Цемент М400", к["бетон"])

    data = _json(
        люди["admin"], f"?pick=1&format=json&category={к['мебель']}&keywords=1&status=active"
    )

    assert _заголовки(data) == {"Офисный стол руководителя", "Диван угловой", "ЛДСП Egger 16 мм"}
    стол = next(i for i in data["items"] if i["title"] == "Офисный стол руководителя")
    assert стол["url"].endswith("/listing/" + стол["url"].rsplit("/", 1)[1])
    assert стол["admin_url"].endswith(f"/py/admin/data/listing/{стол['id']}/change/")
    assert стол["category"]["name"] == "Офисная мебель"
    assert стол["category"]["parent"]["name"] == "Мебель"
    assert стол["company"]["name"] == "Мебель Плюс" and "/company/co-" in стол["company"]["url"]
    тело = json.dumps(data, ensure_ascii=False)
    assert "+998901234567" not in тело and "sales@example.com" not in тело, "без контактов"

    строка = журнал("exported")
    assert строка["section"] == "listings"
    [(note,)] = sql("select note from admin_actions where action = 'exported'")
    assert note == "Формат: JSON; категории: Мебель; плюс мебельные слова; только опубликованные"


def test_подкатегория_все_статусы_в_csv(люди):
    к = _каталог()
    _объявление("Диван угловой", к["дом"])
    _объявление("Шкаф-купе на проверке", к["дом"], status="moderation")
    _объявление("Офисный стол руководителя", к["офис"])
    удалённый = _объявление("Кровать в корзине", к["дом"])
    sql("update listings set deleted_at = now() where id = %s", [удалённый])

    _, ответ = django(
        люди["admin"], ("get", EXPORT + f"?pick=1&format=csv&category={к['дом']}&status=all", None)
    )
    строки = list(csv.DictReader(io.StringIO(ответ["body"].lstrip("﻿"))))

    assert {r["Заголовок"] for r in строки} == {"Диван угловой", "Шкаф-купе на проверке"}
    assert all(r["Ссылка на сайте"].startswith("http") for r in строки)
    assert {r["Категория"] for r in строки} == {"Мебель › Мебель для дома"}
    assert {r["Статус"] for r in строки} == {"Активно", "На проверке"}


def test_слова_правятся_в_настройке(люди):
    к = _каталог()
    _объявление("Стулья венские", к["бетон"])
    _объявление("Пристулок садовый", к["бетон"])
    _объявление("Столешница из камня", к["бетон"])

    по_умолчанию = _json(люди["admin"], "?pick=1&format=json&keywords=1")
    sql(
        'insert into settings ("group", key, label, type, value, sort, created_at, updated_at) '
        "values ('integrations', 'furniture_keywords', 'Мебельные слова', 'text', %s, 0, "
        "now(), now())",
        [json.dumps("столешниц")],
    )
    свои = _json(люди["admin"], "?pick=1&format=json&keywords=1")

    assert _заголовки(по_умолчанию) == {"Стулья венские", "Столешница из камня"}
    assert _заголовки(свои) == {"Столешница из камня"}


def test_тип_и_все_категории(люди):
    к = _каталог()
    _объявление("Диван угловой", к["дом"])
    _объявление("Куплю цемент", к["бетон"], type="demand")

    все = _json(люди["admin"], "?pick=1&format=json")
    запросы = _json(люди["admin"], "?pick=1&format=json&type=demand")

    assert _заголовки(все) == {"Диван угловой", "Куплю цемент"}
    assert _заголовки(запросы) == {"Куплю цемент"}


def test_как_на_экране_и_права(люди):
    к = _каталог()
    _объявление("Диван угловой", к["дом"])
    _объявление("Шкаф-купе на проверке", к["дом"], status="moderation")

    как_на_экране = _json(люди["admin"], "?status=moderation&format=json")
    _, модератор = django(люди["moderator"], ("get", EXPORT + "?pick=1&format=json", None))
    _, страница = django(люди["admin"], ("get", "/py/admin/data/listing/", None))

    assert _заголовки(как_на_экране) == {"Шкаф-купе на проверке"}
    assert модератор["status"] == 403
    assert (
        'id="sx-export"' in страница["body"]
        and "Мебель и всё, что с ней связано" in страница["body"]
    )
