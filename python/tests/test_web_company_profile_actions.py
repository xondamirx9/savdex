"""
Профиль своей компании на Django неотличим от Laravel: правка (ИНН по
правилу Tin и одна компания на ИНН, год основания, IT-направления,
search_text), создание компании пользователем без неё (адрес из
названия, владелец, переход в профиль); у администратора — журнал.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .pg_admin import php, sql, нужна_база, свежая_база, страна
from .test_web_forms import inertia, отправить, учётка
from .web_site import laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    страна("kz", {"ru": "Казахстан"})
    php(
        f"App\\Models\\Company::factory()->create(['slug' => 'mine', 'country_id' => {uz},"
        " 'name' => 'Цемент Трейд', 'tin' => '301234567']);"
        "App\\Models\\Company::factory()->create(['slug' => 'other', 'tin' => '305123456']);"
        "App\\Models\\Company::factory()->create(['slug' => 'cement-plus'])->delete();"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


def _страна(code: str) -> int:
    return int(sql("select id from countries where code = %s", [code])[0][0])


def _компания(slug: str) -> int:
    return int(sql("select id from companies where slug = %s", [slug])[0][0])


def сброс(admin: bool = False, без_компании: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions where section in ('companies', 'users')")
        # Созданная прошлой стороной компания — прочь, номер — тот же
        sql("update users set company_id = null where email = 'owner@savdex.uz'")
        sql("delete from companies where slug not in ('mine', 'other') and deleted_at is null")
        sql("select setval('companies_id_seq', (select max(id) from companies) + 1, false)")
        sql(
            "update companies set name = 'Цемент Трейд', legal_name = null, tin = '301234567', "
            "country_id = %s, founded_year = null, is_it_provider = false, "
            "it_specializations = null, search_text = 'цемент трейд sement treyd', "
            "updated_at = now() - interval '1 day' where slug = 'mine'",
            [_страна("uz")],
        )
        учётка(
            "owner@savdex.uz",
            company_id=None if без_компании else _компания("mine"),
            company_role="owner",
            is_admin=admin,
        )

    return run


def снимок() -> Any:
    журнал = [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions "
            "where section in ('companies', 'users') order by id"
        )
    ]

    return {
        "companies": sql(
            "select id, slug, name, legal_name, tin, country_id, founded_year, is_it_provider, "
            "it_specializations::text, search_text, status, deleted_at is not null, "
            "updated_at > now() - interval '1 hour' from companies order by id"
        ),
        "owner": sql("select company_id, company_role from users where email = 'owner@savdex.uz'"),
        "journal": журнал,
    }


ВЕРНО = {
    "name": "Цемент Плюс",
    "legal_name": "ООО «Цемент Плюс»",
    "tin": "302345678",
    "founded_year": "2010",
    "is_it_provider": True,
    "it_specializations": ["web", "erp"],
    "primary_role": "supplier",
    "website": "https://cement.uz",
}


@pytest.mark.parametrize(
    "body",
    [
        ВЕРНО,
        {"name": "Цемент Трейд", "tin": "301234567"},
        {**ВЕРНО, "tin": "30234567"},
        {**ВЕРНО, "tin": "30234567a"},
        {**ВЕРНО, "tin": "111111111"},
        {**ВЕРНО, "tin": "123456789"},
        {**ВЕРНО, "tin": "305123456"},
        {**ВЕРНО, "tin": "1234567", "country_id": "kz"},
        {**ВЕРНО, "tin": "12345", "country_id": "kz"},
        {**ВЕРНО, "founded_year": "1800"},
        {**ВЕРНО, "it_specializations": ["web", "space"], "primary_role": "boss"},
        {**ВЕРНО, "name": ""},
        {**ВЕРНО, "tin": None, "legal_name": None},
    ],
)
@pytest.mark.parametrize("admin", [False, True])
def test_правка(сайт, body, admin):
    body = dict(body)

    if body.get("country_id") == "kz":
        body["country_id"] = _страна("kz")

    отправить(
        сайт,
        "/cabinet/company",
        сброс(admin),
        снимок,
        uid=учётка("owner@savdex.uz"),
        body=body,
        method="PATCH",
        headers=inertia(),
    )


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_новая_компания(сайт, admin, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/company",
        сброс(admin, без_компании=True),
        снимок,
        uid=учётка("owner@savdex.uz"),
        body={**ВЕРНО, "tin": "309876543"},
        method="PATCH",
        headers=inertia(),
    )

    assert итог["ответ"]["status"] == 303
    assert итог["база"]["owner"][0][1] == "owner"
