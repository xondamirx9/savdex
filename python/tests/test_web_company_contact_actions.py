"""
Контакты своей компании на Django: добавить
(проверка по типу — почта как email:rfc, телефон шаблоном, одно значение
в компании один раз; основной — первый своего типа; порядок — по числу
контактов), изменить, удалить (последний телефон или почту — нельзя).
Без компании — сообщение, чужой контакт — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    компания(slug="mine")
    компания(slug="other")

    with адрес() as root:
        yield root


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def владелец() -> int:
    return учётка("owner@savdex.uz", company_id=_компания("mine"))


def контакты(*строки: tuple[str, str, bool], чужой: bool = True) -> Callable[[], None]:
    """Подготовка: контакты своей компании (тип, значение, основной) и один чужой."""

    def run() -> None:
        sql("delete from company_contacts")
        sql("select setval('company_contacts_id_seq', 1, false)")

        for type_, value, primary in строки:
            sql(
                "insert into company_contacts (company_id, type, value, is_primary, sort_order, "
                "created_at, updated_at) values (%s, %s, %s, %s, 0, now() - interval '1 day', "
                "now() - interval '1 day')",
                [_компания("mine"), type_, value, primary],
            )

        if чужой:
            sql(
                "insert into company_contacts (company_id, type, value, created_at, updated_at) "
                "values (%s, 'phone', '+998 90 000-00-00', now(), now())",
                [_компания("other")],
            )

    return run


def снимок() -> Any:
    return sql(
        "select id, company_id, type, value, label, contact_person, is_primary, is_public, "
        "sort_order, updated_at > now() - interval '1 hour' from company_contacts order by id"
    )


ЕСТЬ = (("phone", "+998 90 111-22-33", True), ("email", "sale@cement.uz", True))

#: Строки до запроса: свои два контакта и чужой телефон
ДО = [
    (1, 1, "phone", "+998 90 111-22-33", None, None, True, True, 0, False),
    (2, 1, "email", "sale@cement.uz", None, None, True, True, 0, False),
    (3, 2, "phone", "+998 90 000-00-00", None, None, False, True, 0, True),
]


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Содержимое сессии после запроса."""
    return json.loads(итог["сессия"]["payload"].replace('"<token>"', '""'))


def ошибки(итог: dict[str, Any]) -> set[str]:
    """Поля с ошибками проверки (errors в сессии)."""
    return set(сессия(итог).get("errors", {}).get("default", {}).get("messages", {}))


@pytest.mark.parametrize(
    ("body", "новый"),
    [
        # Новый контакт: (тип, значение, подпись, контактное лицо, основной, на визитке,
        # порядок); не первый своего типа — не основной; порядок — по числу контактов
        (
            {"type": "phone", "value": "+998 (91) 222 33 44"},
            ("phone", "+998 (91) 222 33 44", None, None, False, True, 2),
        ),
        (
            {"type": "phone", "value": "+998 91 222 33 44", "label": "Склад", "is_public": False},
            ("phone", "+998 91 222 33 44", "Склад", None, False, False, 2),
        ),
        (
            {"type": "email", "value": "info@cement.uz", "contact_person": "Азиз", "sort_order": 3},
            ("email", "info@cement.uz", None, "Азиз", False, True, 3),
        ),
        # email:rfc принимает адрес на кириллице
        (
            {"type": "email", "value": "почта@цемент.уз"},
            ("email", "почта@цемент.уз", None, None, False, True, 2),
        ),
        ({"type": "email", "value": "not-an-email"}, {"value"}),
        ({"type": "email", "value": "a..b@cement.uz"}, {"value"}),
        ({"type": "phone", "value": "12345"}, {"value"}),
        # Первый своего типа — основной
        (
            {"type": "telegram", "value": "@cement_trade"},
            ("telegram", "@cement_trade", None, None, True, True, 2),
        ),
        (
            {"type": "website", "value": "https://cement.uz"},
            ("website", "https://cement.uz", None, None, True, True, 2),
        ),
        ({"type": "fax", "value": "123"}, {"type"}),
        # Одно значение в компании — один раз (чужой такой же телефон не мешает)
        ({"type": "phone", "value": "+998 90 111-22-33"}, {"value"}),
        ({"type": "email", "value": "+998 90 000-00-00"}, {"value"}),
        ({"type": "phone", "value": ["массив"]}, {"value"}),
        ({"type": "phone", "value": "+998 91 222 33 44", "sort_order": 100}, {"sort_order"}),
        ({"type": "phone", "value": "+998 91 222 33 44", "is_public": "on"}, {"is_public"}),
        ({"type": "phone", "value": "+998 91 222 33 44", "label": "x" * 61}, {"label"}),
        ({}, {"type", "value"}),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_добавить(сайт, body, новый, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/company/contacts",
        контакты(*ЕСТЬ),
        снимок,
        uid=владелец(),
        body=body,
        headers=inertia(),
    )
    ответ = итог["ответ"]

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + prefix + "/cabinet/settings"

    if isinstance(новый, set):
        assert ошибки(итог) == новый
        assert итог["база"] == ДО
    else:
        assert ошибки(итог) == set()
        assert сессия(итог)["success"] == ("Contact added" if prefix else "Контакт добавлен")
        assert итог["база"] == [*ДО, (4, 1, *новый, True)]


def test_добавить_первый_своего_типа(сайт):
    итог = отправить(
        сайт,
        "/cabinet/company/contacts",
        контакты(("phone", "+998 90 111-22-33", True)),
        снимок,
        uid=владелец(),
        body={"type": "email", "value": "sale@cement.uz"},
        headers=inertia(),
    )

    assert итог["база"][-1] == (3, 1, "email", "sale@cement.uz", None, None, True, True, 1, True)


def test_добавить_без_компании(сайт):
    uid = учётка("nobody@savdex.uz", company_id=None)
    итог = отправить(
        сайт,
        "/cabinet/company/contacts",
        контакты(*ЕСТЬ),
        снимок,
        uid=uid,
        body={"type": "phone", "value": "+998 91 222 33 44"},
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 302
    assert сессия(итог)["error"] == "Сначала заполните данные компании"
    assert итог["база"] == ДО


@pytest.mark.parametrize(
    ("body", "строка"),
    [
        (
            {"type": "phone", "value": "+998 90 111-22-33", "label": "Офис", "sort_order": "2"},
            (1, 1, "phone", "+998 90 111-22-33", "Офис", None, True, True, 2, True),
        ),
        (
            {"type": "phone", "value": "+998 90 999-88-77", "is_public": "0"},
            (1, 1, "phone", "+998 90 999-88-77", None, None, True, False, 0, True),
        ),
        ({"type": "phone", "value": "sale@cement.uz"}, {"value"}),
        # Уже есть у своей компании
        ({"type": "email", "value": "sale@cement.uz"}, {"value"}),
        # Такой же у чужой компании — можно
        (
            {"type": "phone", "value": "+998 90 000-00-00"},
            (1, 1, "phone", "+998 90 000-00-00", None, None, True, True, 0, True),
        ),
        ({"type": "phone"}, {"value"}),
    ],
)
def test_изменить(сайт, body, строка):
    итог = отправить(
        сайт,
        "/cabinet/company/contacts/1",
        контакты(*ЕСТЬ),
        снимок,
        uid=владелец(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"

    if isinstance(строка, set):
        assert ошибки(итог) == строка
        assert итог["база"] == ДО
    else:
        assert сессия(итог)["success"] == "Контакт обновлён"
        assert итог["база"] == [строка, *ДО[1:]]


ПОСЛЕДНИЙ = "Это последний способ связи. Добавьте другой телефон или почту, прежде чем удалять этот."


@pytest.mark.parametrize(
    ("строки", "номер", "остались", "сообщение"),
    [
        (ЕСТЬ, 1, [2, 3], ("success", "Контакт удалён")),
        # Последний телефон или почту — нельзя
        ((ЕСТЬ[0],), 1, [1, 2], ("error", ПОСЛЕДНИЙ)),
        ((ЕСТЬ[0], ("telegram", "@cement", False)), 2, [1, 3], ("success", "Контакт удалён")),
        # Телеграм не считается способом связи
        ((ЕСТЬ[0], ("telegram", "@cement", False)), 1, [1, 2, 3], ("error", ПОСЛЕДНИЙ)),
    ],
)
def test_удалить(сайт, строки, номер, остались, сообщение):
    итог = отправить(
        сайт,
        f"/cabinet/company/contacts/{номер}",
        контакты(*строки),
        снимок,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )
    ключ, текст = сообщение

    assert итог["ответ"]["status"] == 303
    assert сессия(итог)[ключ] == текст
    assert [row[0] for row in итог["база"]] == остались


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_чужой_контакт_404(сайт, method):
    итог = отправить(
        сайт,
        "/cabinet/company/contacts/3",
        контакты(*ЕСТЬ),
        снимок,
        uid=владелец(),
        body={"type": "phone", "value": "+998 91 222 33 44"},
        method=method,
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"] == ДО
