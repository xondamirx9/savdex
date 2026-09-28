"""
Контакты своей компании на Django неотличимы от Laravel: добавить
(проверка по типу — почта как email:rfc, телефон шаблоном, одно значение
в компании один раз; основной — первый своего типа; порядок — по числу
контактов), изменить, удалить (последний телефон или почту — нельзя).
Без компании — сообщение, чужой контакт — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "App\\Models\\Company::factory()->create(['slug' => 'mine']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
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


@pytest.mark.parametrize(
    "body",
    [
        {"type": "phone", "value": "+998 (91) 222 33 44"},
        {"type": "phone", "value": "+998 91 222 33 44", "label": "Склад", "is_public": False},
        {"type": "email", "value": "info@cement.uz", "contact_person": "Азиз", "sort_order": 3},
        {"type": "email", "value": "почта@цемент.уз"},
        {"type": "email", "value": "not-an-email"},
        {"type": "email", "value": "a..b@cement.uz"},
        {"type": "phone", "value": "12345"},
        {"type": "telegram", "value": "@cement_trade"},
        {"type": "website", "value": "https://cement.uz"},
        {"type": "fax", "value": "123"},
        {"type": "phone", "value": "+998 90 111-22-33"},
        {"type": "email", "value": "+998 90 000-00-00"},
        {"type": "phone", "value": ["массив"]},
        {"type": "phone", "value": "+998 91 222 33 44", "sort_order": 100},
        {"type": "phone", "value": "+998 91 222 33 44", "is_public": "on"},
        {"type": "phone", "value": "+998 91 222 33 44", "label": "x" * 61},
        {},
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_добавить(сайт, body, prefix):
    отправить(
        сайт,
        f"{prefix}/cabinet/company/contacts",
        контакты(*ЕСТЬ),
        снимок,
        uid=владелец(),
        body=body,
        headers=inertia(),
    )


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

    assert итог["база"][-1][6] is True


def test_добавить_без_компании(сайт):
    uid = учётка("nobody@savdex.uz", company_id=None)
    отправить(
        сайт,
        "/cabinet/company/contacts",
        контакты(*ЕСТЬ),
        снимок,
        uid=uid,
        body={"type": "phone", "value": "+998 91 222 33 44"},
        headers=inertia(),
    )


@pytest.mark.parametrize(
    "body",
    [
        {"type": "phone", "value": "+998 90 111-22-33", "label": "Офис", "sort_order": "2"},
        {"type": "phone", "value": "+998 90 999-88-77", "is_public": "0"},
        {"type": "phone", "value": "sale@cement.uz"},
        {"type": "email", "value": "sale@cement.uz"},
        {"type": "phone", "value": "+998 90 000-00-00"},
        {"type": "phone"},
    ],
)
def test_изменить(сайт, body):
    отправить(
        сайт,
        "/cabinet/company/contacts/1",
        контакты(*ЕСТЬ),
        снимок,
        uid=владелец(),
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize(
    ("строки", "номер"),
    [
        (ЕСТЬ, 1),
        ((ЕСТЬ[0],), 1),
        ((ЕСТЬ[0], ("telegram", "@cement", False)), 2),
        ((ЕСТЬ[0], ("telegram", "@cement", False)), 1),
    ],
)
def test_удалить(сайт, строки, номер):
    отправить(
        сайт,
        f"/cabinet/company/contacts/{номер}",
        контакты(*строки),
        снимок,
        uid=владелец(),
        method="DELETE",
        headers=inertia(),
    )


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
