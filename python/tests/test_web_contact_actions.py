"""
«Мои контакты» на Django неотличимы от Laravel: статус и заметка
(PATCH, проверка ввода), жалоба на нерабочий контакт (одна, причина
10–500 знаков, свои тексты ошибок), выгрузка в CSV (BOM, «;», кавычки
как у fputcsv, свежие первыми). Чужое раскрытие — 404.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .pg_admin import php, sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, отправить, учётка
from .test_web_session import СЕССИЯ, завести, кука
from .web_site import laravel, из_django, из_laravel

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'buyer']);"
        "$t = App\\Models\\Company::factory()->create(['slug' => 'target',"
        " 'name' => 'ООО «Цемент; Трейд»']);"
        "$t->contacts()->create(['type' => 'phone', 'value' => '+998 90 111-22-33',"
        " 'is_public' => true]);"
        "$t->contacts()->create(['type' => 'email', 'value' => 'sale@cement.uz',"
        " 'is_public' => true, 'is_primary' => true]);"
        "$t2 = App\\Models\\Company::factory()->create(['slug' => 'target-2',"
        " 'name' => 'Бетон \\\\\"Юг\\\" сервис']);"
        "$o = App\\Models\\Company::factory()->create(['slug' => 'other-buyer']);"
        "foreach ([[$c, $t, 'Первый'], [$c, $t2, 'Второй \"важный\"'], [$o, $t, 'Чужой']]"
        " as $i => [$who, $to, $note]) {"
        " App\\Models\\ContactUnlock::factory()->create(['company_id' => $who->id,"
        " 'target_company_id' => $to->id, 'note' => $note, 'status' => 'new',"
        " 'created_at' => now()->subDays(3 - $i)]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel(MACHINE_TRANSLATION_ENABLED="false") as root:
        yield root


def покупатель() -> int:
    cid = int(sql("select id from companies where slug = 'buyer'")[0][0])

    return учётка("buyer@savdex.uz", company_id=cid)


def раскрытия(slug: str = "buyer") -> list[int]:
    return [
        int(r[0])
        for r in sql(
            "select u.id from contact_unlocks u join companies c on c.id = u.company_id "
            "where c.slug = %s order by u.id",
            [slug],
        )
    ]


def сброс(жалоба: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql(
            "update contact_unlocks set status = 'new', note = 'Первый', complaint_status = %s, "
            "complaint_reason = null, complained_at = null, "
            "updated_at = now() - interval '1 day' where id = %s",
            ["pending" if жалоба else None, раскрытия()[0]],
        )

    return run


def снимок() -> Any:
    return sql(
        "select status, note, complaint_status, complaint_reason, complained_at is not null, "
        "updated_at > now() - interval '1 hour' from contact_unlocks order by id"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"status": "deal", "note": "  Договорились о поставке  "},
        {"status": "deal"},
        {"note": ""},
        {"status": "Первый"},
        {},
        {"status": "boom", "note": "x" * 501},
        {"note": ["массив"]},
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_статус_и_заметка(сайт, body, prefix):
    отправить(
        сайт,
        f"{prefix}/cabinet/contacts/{раскрытия()[0]}",
        сброс(),
        снимок,
        uid=покупатель(),
        body=body,
        method="PATCH",
    )


@pytest.mark.parametrize(
    ("body", "жалоба"),
    [
        ({"reason": "Телефон не отвечает третий день подряд"}, False),
        ({"reason": "коротко"}, False),
        ({}, False),
        ({"reason": "x" * 501}, False),
        ({"reason": "Телефон не отвечает третий день подряд"}, True),
    ],
)
def test_жалоба(сайт, body, жалоба):
    отправить(
        сайт,
        f"/cabinet/contacts/{раскрытия()[0]}/complaint",
        сброс(жалоба),
        снимок,
        uid=покупатель(),
        body=body,
    )


def test_чужое_раскрытие_404(сайт):
    итог = отправить(
        сайт,
        f"/cabinet/contacts/{раскрытия('other-buyer')[0]}",
        lambda: None,
        снимок,
        uid=покупатель(),
        body={"status": "deal"},
        method="PATCH",
    )

    assert итог["ответ"]["status"] == 404


@pytest.mark.parametrize("prefix", ["", "/en"])
def test_выгрузка_csv(сайт, prefix):
    uid = покупатель()
    ответы = []

    for сторона in (из_django, из_laravel):
        завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
        ответы.append(
            сторона(сайт, f"{prefix}/cabinet/contacts/export", {СЕССИЯ: кука(СЕССИЯ, SID)})
        )

    д, л = ответы

    assert д["status"] == л["status"] == 200
    assert д["body"] == л["body"], (д["body"], л["body"])
    assert д["headers"]["content-disposition"] == л["headers"]["content-disposition"]
    assert д["body"].startswith("﻿") and "Второй" in д["body"]
    # Кавычка после обратной косой не удваивается (escape у fputcsv)
    assert '"Бетон \\"Юг\\" сервис"' in д["body"], д["body"]
    for header in ("content-type", "x-ratelimit-limit", "x-ratelimit-remaining"):
        assert д["headers"].get(header) == л["headers"].get(header), header
