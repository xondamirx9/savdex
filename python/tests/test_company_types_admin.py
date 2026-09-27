"""
Раздел «Типы компаний» админки на Django — сквозь настоящую базу.

Пять типов заводит сама миграция Laravel (manufacturer, importer, …),
на них и проверяется: права по ролям, код (вид, нижний регистр,
неизменность), русское название, запрет удаления используемого типа
и строки журнала admin_actions.

Нужны PHP (миграции) и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

LIST = "/py/admin/catalogs/companytype/"
ADD = "/py/admin/catalogs/companytype/add/"


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    sql(
        "insert into companies (name, slug, type, created_at, updated_at) "
        "values ('ООО «Завод»', 'zavod', 'manufacturer', now(), now())"
    )

    return {
        role: сотрудник(role) for role in ("superadmin", "content_manager", "moderator", "sales")
    }


def _тип(code: str) -> int:
    [(pk,)] = sql("select id from company_types where code = %s", [code])

    return int(pk)


def _форма(code: str, names: dict[str, str], *, type_id: int | None = None) -> dict[str, Any]:
    """Поля формы типа вместе с формами переводов — как их шлёт браузер."""
    ids = {}
    if type_id is not None:
        ids = dict(
            sql(
                "select locale, id from company_type_translations where company_type_id = %s",
                [type_id],
            )
        )

    data: dict[str, Any] = {
        "code": code,
        "sort": "7",
        "is_active": "on",
        "translations-TOTAL_FORMS": str(len(names)),
        "translations-INITIAL_FORMS": str(len([loc for loc in names if loc in ids])),
        "translations-MIN_NUM_FORMS": "1",
        "translations-MAX_NUM_FORMS": "5",
    }

    for i, (locale, name) in enumerate(names.items()):
        data[f"translations-{i}-locale"] = locale
        data[f"translations-{i}-name"] = name
        if locale in ids:
            data[f"translations-{i}-id"] = str(ids[locale])
            data[f"translations-{i}-company_type"] = str(type_id)

    return data


def test_список_и_права(люди):
    вход, список = django(люди["moderator"], ("get", LIST, None))

    assert вход == 302
    assert список["status"] == 200
    assert "Производитель · manufacturer" in список["body"]
    assert "5 из 5" in список["body"]

    # Модератор смотрит, но не заводит
    _, заведение = django(люди["moderator"], ("get", ADD, None))
    assert заведение["status"] == 403

    # Отделу продаж справочники не выданы
    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_типа_и_журнал(люди):
    _, ответ = django(
        люди["content_manager"],
        ("post", ADD, _форма(" Logistics ", {"ru": "Логистика", "en": "Logistics"})),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    [(sort, active)] = sql("select sort, is_active from company_types where code = 'logistics'")
    assert (sort, active) == (7, True)

    запись = журнал("created")
    assert запись["user_role"] == "content_manager"
    assert запись["section"] == "catalogs"
    assert запись["subject_type"] == "App\\Models\\CompanyType"
    assert запись["subject_label"] == "logistics"
    after = запись["changes"]["after"]
    assert after["code"] == "logistics" and after["name:ru"] == "Логистика"


@pytest.mark.parametrize("code", ["Логистика", "raw materials", "-x", "a__b"])
def test_код_латиницей(люди, code):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма(code, {"ru": "Тип"})))

    assert ответ["status"] == 200
    assert "Только латиница, цифры, дефис и подчёркивание" in ответ["body"]


def test_повтор_кода_в_другом_регистре_не_проходит(люди):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма("IMPORTER", {"ru": "Дубль"})))

    assert ответ["status"] == 200
    assert "Тип с таким кодом уже есть" in ответ["body"]
    assert sql("select count(*) from company_types where code = 'importer'") == [(1,)]


def test_без_русского_названия_не_сохраняется(люди):
    _, ответ = django(
        люди["content_manager"], ("post", ADD, _форма("contractor", {"en": "Contractor"}))
    )

    assert ответ["status"] == 200
    assert "Нужно русское название" in ответ["body"]
    assert sql("select count(*) from company_types where code = 'contractor'") == [(0,)]


def test_код_после_создания_не_меняется(люди):
    """Код записан в карточках компаний: его смена оставила бы их без типа."""
    pk = _тип("logistics")
    данные = _форма("shipping", {"ru": "Перевозки", "en": "Logistics"}, type_id=pk)

    _, форма, ответ = django(
        люди["content_manager"],
        ("get", f"{LIST}{pk}/change/", None),
        ("post", f"{LIST}{pk}/change/", данные),
    )

    assert 'name="code"' not in форма["body"]
    assert ответ["status"] == 302, ответ["body"][:3000]
    assert sql("select code from company_types where id = %s", [pk]) == [("logistics",)]
    assert журнал("updated")["changes"] == {
        "before": {"name:ru": "Логистика"},
        "after": {"name:ru": "Перевозки"},
    }


def test_удаление(люди):
    manufacturer, logistics = _тип("manufacturer"), _тип("logistics")

    # Контент-менеджеру удаление не выдано
    _, чужое = django(
        люди["content_manager"], ("post", f"{LIST}{logistics}/delete/", {"post": "yes"})
    )
    assert чужое["status"] == 403

    # Тип выбран компанией — удалить нельзя даже суперадмину, форма объясняет почему
    _, форма, занятый = django(
        люди["superadmin"],
        ("get", f"{LIST}{manufacturer}/change/", None),
        ("post", f"{LIST}{manufacturer}/delete/", {"post": "yes"}),
    )
    assert "Нельзя, на тип ссылаются: компании — 1" in форма["body"]
    assert занятый["status"] == 403
    assert sql("select count(*) from company_types where id = %s", [manufacturer]) == [(1,)]

    # Свободный — можно, вместе с переводами; удаление — в журнале
    _, свободный = django(
        люди["superadmin"], ("post", f"{LIST}{logistics}/delete/", {"post": "yes"})
    )
    assert свободный["status"] == 302
    assert sql("select count(*) from company_types where id = %s", [logistics]) == [(0,)]
    assert sql(
        "select count(*) from company_type_translations where company_type_id = %s", [logistics]
    ) == [(0,)]
    assert журнал("deleted")["subject_label"] == "logistics"


def test_компания_в_корзине_тоже_держит_тип(люди):
    """Восстановленная из корзины компания вернулась бы с типом в никуда."""
    sql(
        "insert into companies (name, slug, type, deleted_at, created_at, updated_at) "
        "values ('ООО «Склад»', 'sklad', 'distributor', now(), now(), now())"
    )
    pk = _тип("distributor")

    _, удаление = django(люди["superadmin"], ("post", f"{LIST}{pk}/delete/", {"post": "yes"}))

    assert удаление["status"] == 403
    assert sql("select count(*) from company_types where id = %s", [pk]) == [(1,)]
