"""
Поиск в админке без учёта регистра в любой локали базы (savdex/search.py).

Если база заведена с локалью C, UPPER меняет только латиницу, и обычный
icontains Django не находит «Мебель Плюс» по «мебель» — поиск работал
«только по первой букве». Проверки ставят столбцам локаль C (как у такой
базы) и ищут строчными, с «е» вместо «ё», по ИНН, по номеру и
несколькими словами — в разделах на общем поиске, в справочниках и на
доске CRM.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL) — кроме проверок самого шаблона.
"""

from __future__ import annotations

from urllib.parse import urlencode

import pytest

from savdex import search

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

# ── Шаблон ──────────────────────────────────────────────────────────


def test_шаблон_без_регистра():
    assert search.pattern("Мебель") == "[мМ][еЕёЁ][бБ][еЕёЁ][лЛ][ьЬ]"
    assert search.pattern("O'z") == "[oO][ʻʼ’'`‘][zZ]"
    assert search.pattern("a.b(1)") == r"[aA]\.[bB]\(1\)"


def test_слова_запроса():
    assert search.terms('ООО "Мебель Плюс" 12') == ["ООО", "Мебель Плюс", "12"]
    assert search.terms("  ") == []


# ── В базе с локалью C ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()
    # Как в базе, заведённой с локалью C: UPPER не трогает кириллицу
    for table, column, size in (
        ("companies", "name", 190),
        ("listings", "title", 255),
        ("category_translations", "name", 190),
        ("crm_leads", "title", 200),
    ):
        sql(f'alter table {table} alter column {column} type varchar({size}) collate "C"')

    return {role: сотрудник(role) for role in ("superadmin", "sales")}


def _список(uid: int, url: str, q: str) -> str:
    _, ответ = django(uid, ("get", url + "?" + urlencode({"q": q}), None))
    assert ответ["status"] == 200, ответ["body"][:500]

    return str(ответ["body"])


@нужна_база
def test_так_ломался_icontains(люди):
    """Условие ошибки: в локали C «мебель» и «Мебель» для UPPER разные."""
    assert sql("select upper('мебель' collate \"C\")") == [("мебель",)]


@нужна_база
def test_компании(люди):
    sql("delete from listings")
    sql("delete from companies")
    sql(
        "insert into companies (name, legal_name, tin, slug, status, created_at, updated_at) "
        "values ('Мебель Плюс', 'ООО «Мебельная фабрика»', '301234567', 'mebel-plus', "
        "'active', now(), now()), ('Ёлка-Строй', null, null, 'yolka', 'active', now(), now()), "
        "('Стройбаза', null, null, 'stroybaza', 'active', now(), now())"
    )
    url = "/py/admin/data/companyrecord/"

    assert "Мебель Плюс" in _список(люди["superadmin"], url, "мебель")
    assert "Стройбаза" not in _список(люди["superadmin"], url, "мебель")
    assert "Ёлка-Строй" in _список(люди["superadmin"], url, "елка")
    assert "Мебель Плюс" in _список(люди["superadmin"], url, "301234567"), "по ИНН"
    assert "Мебель Плюс" in _список(люди["superadmin"], url, "мебельная фабрика"), "юр. название"
    несколько = _список(люди["superadmin"], url, "строй ёлка")
    assert "Ёлка-Строй" in несколько and "Стройбаза" not in несколько


@нужна_база
def test_объявления_и_номер(люди):
    sql("delete from listings")
    sql("delete from companies")
    [(company,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) values "
        "('Стройбаза', 'stroybaza', 'active', now(), now()) returning id"
    )
    [(pk,)] = sql(
        "insert into listings (company_id, title, type, status, currency, created_at, "
        "updated_at) values (%s, 'Цемент М400 навалом', 'supply', 'active', 'UZS', now(), "
        "now()) returning id",
        [company],
    )
    sql(
        "insert into listings (company_id, title, type, status, currency, created_at, "
        "updated_at) values (%s, 'Щебень 5-20', 'supply', 'active', 'UZS', now(), now())",
        [company],
    )
    url = "/py/admin/data/listing/"

    по_слову = _список(люди["superadmin"], url, "цемент")
    по_номеру = _список(люди["superadmin"], url, str(pk))

    assert "Цемент М400 навалом" in по_слову and "Щебень 5-20" not in по_слову
    assert "Цемент М400 навалом" in по_номеру and "Щебень 5-20" not in по_номеру


@нужна_база
def test_справочник_по_названию(люди):
    sql("delete from listings")
    sql("delete from category_translations")
    sql("delete from categories")
    [(pk,)] = sql(
        "insert into categories (slug, sort, is_active, created_at, updated_at) "
        "values ('mebel', 0, true, now(), now()) returning id"
    )
    sql(
        "insert into category_translations (category_id, locale, name, created_at, updated_at) "
        "values (%s, 'ru', 'Мебель', now(), now())",
        [pk],
    )

    assert "mebel" in _список(люди["superadmin"], "/py/admin/catalogs/category/", "мебель")


@нужна_база
def test_доска_crm(люди):
    sql("delete from crm_leads")
    sql(
        "insert into crm_leads (title, owner_id, status, source, created_at, updated_at) "
        "values ('Диван угловой', %s, 'new', 'site', now(), now()), "
        "('Цемент М400', %s, 'new', 'site', now(), now())",
        [люди["sales"], люди["sales"]],
    )

    доска = _список(люди["sales"], "/py/admin/crm/lead/", "диван")

    assert "Диван угловой" in доска and "Цемент М400" not in доска
