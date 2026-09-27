"""
Раздел «Страны» админки на Django — сквозь настоящую базу.

PostgreSQL со схемой Laravel (migrate:fresh), сотрудники с разными
ролями входят по пропуску и работают с разделом так, как работали бы
в браузере: список, заведение, правка, удаление. Проверяются права
(AdminAccess), правила Country (код строчными, запрет удаления при
ссылках, русское название) и строки журнала admin_actions.

Нужны PHP (миграции) и PostgreSQL (SAVDEX_PARITY_PG_URL); общая
часть — в pg_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from .pg_admin import django, sql, журнал, нужна_база, свежая_база, сотрудник, страна

pytestmark = нужна_база


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    uz = страна("uz", {"ru": "Узбекистан", "en": "Uzbekistan"})
    sql(
        "insert into cities (country_id, slug, created_at, updated_at) "
        "values (%s, 'tashkent', now(), now())",
        [uz],
    )

    return {
        role: сотрудник(role) for role in ("superadmin", "content_manager", "moderator", "sales")
    }


def _форма(
    code: str, names: dict[str, str], *, country_id: int | None = None, existing: int = 0
) -> dict[str, Any]:
    """Поля формы страны вместе с формами переводов — как их шлёт браузер."""
    data: dict[str, Any] = {
        "code": code,
        "phone_code": "+996",
        "currency_code": "KGS",
        "sort": "5",
        "is_active": "on",
        "translations-TOTAL_FORMS": str(len(names)),
        "translations-INITIAL_FORMS": str(existing),
        "translations-MIN_NUM_FORMS": "1",
        "translations-MAX_NUM_FORMS": "5",
    }

    ids = {}
    if country_id is not None:
        ids = dict(
            sql("select locale, id from country_translations where country_id = %s", [country_id])
        )

    for i, (locale, name) in enumerate(names.items()):
        data[f"translations-{i}-locale"] = locale
        data[f"translations-{i}-name"] = name
        if locale in ids:
            data[f"translations-{i}-id"] = str(ids[locale])
            data[f"translations-{i}-country"] = str(country_id)

    return data


LIST = "/py/admin/geo/country/"
ADD = "/py/admin/geo/country/add/"


def test_список_и_права_на_просмотр(люди):
    вход, список = django(люди["moderator"], ("get", LIST, None))

    assert вход == 302
    assert список["status"] == 200
    assert "Узбекистан · UZ" in список["body"]
    assert "1 из 5" not in список["body"] and "2 из 5" in список["body"]

    # Модератор смотрит, но не заводит
    _, заведение = django(люди["moderator"], ("get", ADD, None))
    assert заведение["status"] == 403

    # Отделу продаж справочники не выданы
    _, чужой = django(люди["sales"], ("get", LIST, None))
    assert чужой["status"] == 403


def test_заведение_страны_и_журнал(люди):
    _, ответ = django(
        люди["content_manager"],
        ("post", ADD, _форма(" KG ", {"ru": "Кыргызстан", "en": "Kyrgyzstan"})),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    [(code, _phone)] = sql("select code, phone_code from countries where phone_code = '+996'")
    assert code == "kg"

    names = dict(
        sql(
            "select locale, name from country_translations t join countries c "
            "on c.id = t.country_id where c.code = 'kg'"
        )
    )
    assert names == {"ru": "Кыргызстан", "en": "Kyrgyzstan"}

    запись = журнал("created")
    assert запись["user_name"] == "Сотрудник content_manager"
    assert запись["user_role"] == "content_manager"
    assert запись["section"] == "catalogs"
    assert запись["subject_type"] == "App\\Models\\Country"
    assert запись["subject_label"] == "kg"
    assert запись["ip"] == "203.0.113.7"
    after = запись["changes"]["after"]
    assert after["code"] == "kg" and after["name:ru"] == "Кыргызстан"
    assert "created_at" not in after and "updated_at" not in after


def test_повтор_кода_в_другом_регистре_не_проходит(люди):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма("UZ", {"ru": "Дубль"})))

    assert ответ["status"] == 200
    assert "Страна с таким кодом уже есть" in ответ["body"]
    assert sql("select count(*) from countries where code = 'uz'") == [(1,)]


def test_без_русского_названия_не_сохраняется(люди):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма("tj", {"en": "Tajikistan"})))

    assert ответ["status"] == 200
    assert "Нужно русское название" in ответ["body"]
    assert sql("select count(*) from countries where code = 'tj'") == [(0,)]


def test_правка_и_переименование_попадают_в_журнал(люди):
    [(kg,)] = sql("select id from countries where code = 'kg'")
    данные = _форма("kg", {"ru": "Киргизия", "en": "Kyrgyzstan"}, country_id=kg, existing=2)
    данные["phone_code"] = "+9960"

    _, ответ = django(люди["content_manager"], ("post", f"{LIST}{kg}/change/", данные))

    assert ответ["status"] == 302, ответ["body"][:3000]
    запись = журнал("updated")
    assert запись["changes"] == {
        "before": {"phone_code": "+996", "name:ru": "Кыргызстан"},
        "after": {"phone_code": "+9960", "name:ru": "Киргизия"},
    }


def test_удаление(люди):
    [(kg,)] = sql("select id from countries where code = 'kg'")
    [(uz,)] = sql("select id from countries where code = 'uz'")

    # Контент-менеджеру удаление не выдано
    _, чужое = django(люди["content_manager"], ("post", f"{LIST}{kg}/delete/", {"post": "yes"}))
    assert чужое["status"] == 403

    # На Узбекистан ссылается город — удалить нельзя даже суперадмину
    _, занятая = django(люди["superadmin"], ("post", f"{LIST}{uz}/delete/", {"post": "yes"}))
    assert занятая["status"] == 403
    assert sql("select count(*) from countries where id = %s", [uz]) == [(1,)]

    # Свободную — можно, вместе с переводами; удаление — в журнале
    _, свободная = django(люди["superadmin"], ("post", f"{LIST}{kg}/delete/", {"post": "yes"}))
    assert свободная["status"] == 302
    assert sql("select count(*) from countries where id = %s", [kg]) == [(0,)]
    assert sql("select count(*) from country_translations where country_id = %s", [kg]) == [(0,)]
    assert журнал("deleted")["subject_label"] == "kg"


def test_правка_формы_показывает_почему_нельзя_удалить(люди):
    [(uz,)] = sql("select id from countries where code = 'uz'")

    _, форма = django(люди["superadmin"], ("get", f"{LIST}{uz}/change/", None))

    assert форма["status"] == 200
    assert "Нельзя, на страну ссылаются: города — 1" in форма["body"]


def test_резюме_тоже_удерживает_страну(люди):
    """
    Резюме ссылаются на страну, но PHP-версия их не считала: удаление
    страны молча обнуляло её у резюме. Теперь резюме удерживают страну
    в обеих половинах.
    """
    [(tj,)] = sql(
        "insert into countries (code, phone_code, currency_code, created_at, updated_at) "
        "values ('tj', '+992', 'TJS', now(), now()) returning id"
    )
    sql(
        "insert into resumes (user_id, title, country_id, created_at, updated_at) "
        "values (%s, 'Инженер', %s, now(), now())",
        [люди["sales"], tj],
    )

    _, форма, удаление = django(
        люди["superadmin"],
        ("get", f"{LIST}{tj}/change/", None),
        ("post", f"{LIST}{tj}/delete/", {"post": "yes"}),
    )

    assert "Нельзя, на страну ссылаются: резюме — 1" in форма["body"]
    assert удаление["status"] == 403
    assert sql("select count(*) from countries where id = %s", [tj]) == [(1,)]
