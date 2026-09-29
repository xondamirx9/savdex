"""
IT-задачи на Django, этап 6: раздел вместо Filament.

- список: компания под названием, вид услуги, откликов, «На сайте» и
  «Снять» у открытой; создавать из админки нельзя;
- правка: стек через запятую — список JSON, search_text заново, строка
  журнала; бюджет не меньше нуля;
- «Снять» — в архив и дата закрытия, строка журнала;
- поддержка смотрит, но не правит; удаление — суперадмин.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/data/ittask/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "moderator", "support")}


@pytest.fixture(autouse=True)
def чисто() -> None:
    sql("delete from it_tasks")
    sql("delete from companies")
    sql("delete from admin_actions where section = 'ittasks'")


def _задача(title: str = "Сайт для склада", **поля: Any) -> int:
    [(company,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) "
        "values ('Стройбаза', %s, 'active', now(), now()) returning id",
        [f"company-{title.lower().replace(' ', '-')}"],
    )
    строка = {
        "slug": title.lower().replace(" ", "-"),
        "description": "Нужен сайт для учёта остатков на складе.",
        "service_type": "web",
        "budget_type": "negotiable",
        "currency": "UZS",
        "status": "active",
        **поля,
    }
    columns = ["company_id", "title", *строка]
    [(pk,)] = sql(
        f"insert into it_tasks ({', '.join(columns)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(columns))}, now(), now()) returning id",
        [company, title, *строка.values()],
    )

    return int(pk)


def _форма(**поля: str) -> dict[str, str]:
    return {
        "title": "Сайт для склада",
        "description": "Нужен сайт для учёта остатков на складе.",
        "service_type": "web",
        "stack": "",
        "budget_type": "fixed",
        "budget_from": "5000000",
        "budget_to": "",
        "currency": "UZS",
        "deadline_at": "",
        "status": "active",
        **поля,
    }


def test_список_и_создание(люди):
    pk = _задача()
    _задача("Бот для заказов", status="archived")

    _, список, создать = django(
        люди["moderator"], ("get", LIST, None), ("get", LIST + "add/", None)
    )

    assert "Стройбаза" in список["body"] and "Сайты и веб-приложения" in список["body"]
    assert 'href="/it-services/сайт-для-склада"' in список["body"]
    assert f"{LIST}{pk}/archive/" in список["body"]
    assert создать["status"] == 403, "задачи заводятся только в кабинете"


def test_правка_стек_и_поиск(люди):
    pk = _задача()

    _, ответ = django(
        люди["moderator"],
        ("post", f"{LIST}{pk}/change/", _форма(stack="Laravel, React , ", title="Сайт склада")),
    )

    assert ответ["status"] == 302, ответ["body"][:1500]
    [(stack, search, title)] = sql("select stack::text, search_text, title from it_tasks")
    assert stack == '["Laravel","React"]' or stack == '["Laravel", "React"]'
    assert title == "Сайт склада" and "react" in search.lower()
    assert журнал("updated")["section"] == "ittasks"


def test_бюджет_не_меньше_нуля(люди):
    pk = _задача()

    _, ответ = django(люди["moderator"], ("post", f"{LIST}{pk}/change/", _форма(budget_from="-1")))

    assert ответ["status"] == 200
    assert sql("select budget_from from it_tasks") == [(None,)]


def test_снять(люди):
    pk = _задача()

    _, ответ = django(люди["moderator"], ("post", f"{LIST}{pk}/archive/", {}))

    assert ответ["status"] == 302
    assert sql("select status, closed_at is not null from it_tasks") == [("archived", True)]
    assert журнал("updated")["changes"]["after"]["status"] == "archived"


def test_поддержка_смотрит_удаление_суперадмином(люди):
    pk = _задача()

    _, список, правка, снять = django(
        люди["support"],
        ("get", LIST, None),
        ("post", f"{LIST}{pk}/change/", _форма(title="Взлом")),
        ("post", f"{LIST}{pk}/archive/", {}),
    )
    _, удалено = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))

    assert список["status"] == 200 and f"{LIST}{pk}/archive/" not in список["body"]
    assert (правка["status"], снять["status"]) == (403, 403)
    assert удалено["status"] == 302
    assert sql("select count(*) from it_tasks") == [(0,)]
