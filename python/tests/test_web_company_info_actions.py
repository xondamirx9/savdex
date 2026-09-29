"""
Данные компании в настройках на Django неотличимы от Laravel (ответы JSON):
сведения и справочники; сохранение — заполнить пустое можно всегда, смена
заполненного ставит метку и закрывает смену на полгода, пока срок идёт —
422 с полями; проверка как у профиля компании; обращение в поддержку.
Только владелец компании.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база, страна
from .test_web_forms import xsrf, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база

ПОЧТА = "info@savdex.uz"
JSON = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "X-XSRF-TOKEN": xsrf(),
}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    php(
        f"App\\Models\\Company::factory()->create(['slug' => 'mine', 'country_id' => {uz},"
        " 'name' => 'Цемент Трейд', 'tin' => '301234567', 'legal_name' => null,"
        " 'is_it_provider' => false, 'it_specializations' => null]);"
        "App\\Models\\Company::factory()->create(['slug' => 'other', 'tin' => '305123456']);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def _компания() -> int:
    return int(sql("select id from companies where slug = 'mine'")[0][0])


def сброс(
    *, роль: str = "owner", сменено: str | None = None, admin: bool = False
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from support_messages")
        sql("delete from support_tickets")
        sql("delete from admin_actions")
        sql(
            "update companies set name = 'Цемент Трейд', legal_name = null, tin = '301234567', "
            "founded_year = null, is_it_provider = false, it_specializations = null, "
            "address = null, profile_changed_at = %s, "
            "updated_at = now() - interval '1 day' where slug = 'mine'",
            [сменено],
        )
        учётка(ПОЧТА, company_id=_компания(), company_role=роль, is_admin=admin)

    return run


def снимок() -> Any:
    return {
        "company": sql(
            "select name, legal_name, tin, founded_year, is_it_provider, "
            "it_specializations::text, address, search_text, profile_changed_at is not null, "
            "updated_at > now() - interval '1 hour' from companies where slug = 'mine'"
        ),
        "tickets": sql(
            "select subject, author_name, author_email, status, channel, priority, "
            "closed_at, last_reply_at is not null from support_tickets order by id"
        ),
        "messages": [
            (a, f, i, re.sub(r"#\d+", "#N", b))
            for a, f, i, b in sql(
                "select author_id is not null, from_staff, is_internal, body "
                "from support_messages order by id"
            )
        ],
        "journal": [
            (a, s, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
            for a, s, ch in sql(
                "select action, section, changes::text from admin_actions order by id"
            )
        ],
    }


def запрос(сайт: str, path: str, method: str, body: Any, **настройка: Any) -> dict[str, Any]:
    uid = учётка(ПОЧТА, company_id=_компания())

    return отправить(
        сайт,
        path,
        сброс(**настройка),
        снимок,
        uid=uid,
        method=method,
        body=body,
        headers=JSON,
    )


@pytest.mark.parametrize(
    "настройка",
    [{}, {"сменено": "2026-08-01 10:00:00"}, {"роль": "manager"}],
)
def test_сведения(сайт, настройка):
    запрос(сайт, "/cabinet/settings/company-info", "GET", "", **настройка)


ТЕКУЩЕЕ = {"name": "Цемент Трейд", "tin": "301234567"}


@pytest.mark.parametrize(
    ("body", "настройка"),
    [
        ({**ТЕКУЩЕЕ, "legal_name": "ООО «Цемент Трейд»", "founded_year": "2010"}, {}),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {}),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"сменено": "2026-08-01 10:00:00"}),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"сменено": "2025-01-31 10:00:00"}),
        ({**ТЕКУЩЕЕ, "address": "Ташкент"}, {"сменено": "2026-08-01 10:00:00"}),
        ({**ТЕКУЩЕЕ, "is_it_provider": True, "it_specializations": ["web", "erp"]}, {}),
        ({**ТЕКУЩЕЕ, "tin": "305123456"}, {}),
        ({**ТЕКУЩЕЕ, "tin": "30123"}, {}),
        ({**ТЕКУЩЕЕ, "founded_year": "1800", "it_specializations": ["nope"]}, {}),
        ({"name": ""}, {}),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"admin": True}),
        ({**ТЕКУЩЕЕ, "name": "Цемент Плюс"}, {"роль": "manager"}),
    ],
)
def test_сохранение(сайт, body, настройка):
    запрос(сайт, "/cabinet/settings/company-info", "PATCH", body, **настройка)


@pytest.mark.parametrize(
    ("body", "настройка"),
    [
        ({}, {}),
        ({"message": "коротко"}, {}),
        ({"message": "Поменяйте, пожалуйста, название — мы переименовались."}, {}),
        (
            {"message": "Поменяйте, пожалуйста, название — мы переименовались."},
            {"сменено": "2026-08-01 10:00:00"},
        ),
        ({"message": "Поменяйте, пожалуйста, название."}, {"роль": "manager"}),
    ],
)
def test_обращение(сайт, body, настройка):
    запрос(сайт, "/cabinet/settings/company-info/support", "POST", body, **настройка)
