"""
Админка, «Технические работы»: страницу видят суперадмин, администратор,
модератор и контент-менеджер — у остальных 403. Кнопки «на N минут»,
«до времени», «продлить», «снять» пишут настройку maintenance_until
(время по Ташкенту) и строку журнала; пункт в меню — у тех, кому
страница открыта.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from savdex.web.shared import _TASHKENT

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник

pytestmark = нужна_база

PAGE = "/py/admin/maintenance/"
ROLES = ("superadmin", "admin", "moderator", "content_manager", "finance", "sales", "support")


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ROLES}


def значение() -> str | None:
    rows = sql("select value::text from settings where key = 'maintenance_until'")

    return rows[0][0].strip('"') if rows and rows[0][0] not in (None, "null") else None


def ташкент(minutes: int) -> datetime:
    return datetime.now(UTC).astimezone(_TASHKENT) + timedelta(minutes=minutes)


def около(text: str | None, minutes: int) -> bool:
    """Записанное время — через столько минут (с запасом в пару минут)."""
    assert text
    moment = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=_TASHKENT)

    return abs((moment - ташкент(minutes)).total_seconds()) < 120


@pytest.mark.parametrize("role", ["superadmin", "admin", "moderator", "content_manager"])
def test_кому_открыто(люди, role):
    _, страница, главная = django(люди[role], ("get", PAGE, None), ("get", "/py/admin/", None))

    assert страница["status"] == 200
    assert "Технические работы" in страница["body"] and "На 90 мин" in страница["body"]
    # Пункт в меню слева
    assert f'href="{PAGE}"' in главная["body"]


@pytest.mark.parametrize("role", ["finance", "sales", "support"])
def test_кому_закрыто(люди, role):
    _, страница, главная = django(люди[role], ("get", PAGE, None), ("post", PAGE, {"act": "stop"}))

    assert страница["status"] == 403 and главная["status"] == 403


def test_включить_продлить_снять(люди):
    sql("delete from settings where key = 'maintenance_until'")
    sql("delete from admin_actions where section = 'maintenance'")
    uid = люди["moderator"]

    _, включить = django(uid, ("post", PAGE, {"act": "minutes", "minutes": "90"}))

    assert включить["status"] == 302 and включить["location"] == PAGE
    assert около(значение(), 90)

    django(uid, ("post", PAGE, {"act": "extend"}))
    assert около(значение(), 120)

    _, страница = django(uid, ("get", PAGE, None))
    assert "Сайт закрыт заставкой до" in страница["body"]

    django(uid, ("post", PAGE, {"act": "stop"}))
    assert значение() == ""

    # Продлевать нечего — значение не меняется
    django(uid, ("post", PAGE, {"act": "extend"}))
    assert значение() == ""

    журнал = [
        note
        for (note,) in sql(
            "select note from admin_actions where section = 'maintenance' order by id"
        )
    ]
    assert len(журнал) == 3
    assert журнал[0].startswith("Технические работы включены на 90 мин")
    assert журнал[1].startswith("Технические работы продлены на 30 мин")
    assert журнал[2] == "Технические работы сняты, сайт открыт"


def test_до_времени(люди):
    uid = люди["content_manager"]
    later = ташкент(45).strftime("%Y-%m-%dT%H:%M")
    earlier = ташкент(-10).strftime("%Y-%m-%dT%H:%M")

    django(uid, ("post", PAGE, {"act": "until", "until": later}))
    assert значение() == later.replace("T", " ")

    # Прошедшее время и мусор не принимаются — остаётся прежнее
    django(uid, ("post", PAGE, {"act": "until", "until": earlier}))
    django(uid, ("post", PAGE, {"act": "until", "until": "завтра"}))
    assert значение() == later.replace("T", " ")


@pytest.mark.parametrize("data", [{"act": "minutes", "minutes": "999"}, {"act": "взлом"}])
def test_неизвестное_действие(люди, data):
    _, ответ = django(люди["admin"], ("post", PAGE, data))

    assert ответ["status"] == 404
